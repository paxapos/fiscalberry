# coding=utf-8
"""
Cola de impresión PERSISTENTE (durable) para entornos con conectividad mala.

Por qué existe:
  El camino anterior recibía un mensaje MQTT, lo encolaba en memoria (queue.Queue)
  y hacía ACK al broker ANTES de imprimir. Si la impresora estaba caída, sin papel,
  o el equipo se reiniciaba, el trabajo se perdía en silencio (el broker ya no lo
  reenvía porque cree que se entregó).

Qué hace este spooler:
  1. enqueue(): persiste el trabajo en SQLite. Recién entonces el llamador puede
     hacer ACK al broker -> el trabajo NUNCA se pierde aunque el proceso muera.
  2. Un worker drena la cola persistente e imprime con reintentos (backoff). Si la
     impresora está caída, el job queda 'pending' y se reintenta; sobrevive reinicios.
  3. Dedup por job_id: MQTT QoS1 es "al menos una vez" y puede reentregar el mismo
     mensaje -> INSERT OR IGNORE evita imprimir dos veces el mismo ticket.

El spooler NO sabe de formatos ni de escpos: recibe un dict (ticket) y una función
print_fn(ticket) que imprime y lanza excepción si falla. Así es testeable sin escpos.
"""

import os
import time
import json
import sqlite3
import threading

try:
    from fiscalberry.common.fiscalberry_logger import getLogger
    logger = getLogger()
except Exception:  # pragma: no cover - fallback para tests aislados
    import logging
    logger = logging.getLogger("fiscalberry.print_spooler")

APP_NAME = "fiscalberry"


def default_db_path():
    """Ruta del .db en el data dir del usuario (import diferido para testeo aislado)."""
    import platformdirs
    d = platformdirs.user_data_dir(APP_NAME)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "print_spool.db")


class DurablePrintSpooler:
    def __init__(self, print_fn, db_path=None, max_attempts=1000,
                 base_delay=5.0, max_delay=300.0, idle_wait=5.0):
        """
        print_fn: callable(ticket_dict) -> imprime; lanza excepción si falla.
        max_attempts: tras N intentos el job pasa a 'failed' (dead-letter). Default alto
            (1000) a propósito: con backoff tope 300s son ~3.5 días de reintentos, así una
            impresora caída mucho tiempo NO pierde el ticket. Además, los 'failed' se
            re-encolan al reiniciar el proceso (ver _recover_on_start), así que un
            "apagar y prender" siempre recupera todo lo pendiente.
        """
        self._print_fn = print_fn
        self._db_path = db_path or default_db_path()
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._idle_wait = idle_wait
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        self._init_db()
        self._recover_on_start()
        self._worker = threading.Thread(target=self._run, name="print-spooler", daemon=True)
        self._worker.start()
        logger.info("Spooler durable iniciado (db=%s)", self._db_path)

    def _recover_on_start(self):
        """
        Recuperación al arrancar: garantía de "nunca perder impresiones".

        - Re-encola los dead-letter ('failed' -> 'pending') con presupuesto de
          reintentos fresco: reiniciar el proceso siempre reintenta TODO.
        - Adelanta a "ya" el next_attempt_at de los 'pending' que quedaron esperando
          un backoff previo al cierre, para no demorar la recuperación tras un reinicio.
        """
        with self._lock:
            recovered = self._conn.execute(
                "UPDATE jobs SET status='pending', attempts=0, next_attempt_at=0 "
                "WHERE status='failed'").rowcount
            self._conn.execute(
                "UPDATE jobs SET next_attempt_at=0 WHERE status='pending'")
            self._conn.commit()
        if recovered:
            logger.warning(
                "Spooler: %d job(s) en dead-letter re-encolados tras reinicio", recovered)

    def requeue_failed(self):
        """Vuelve a poner en cola los jobs 'failed' (dead-letter). Devuelve cuántos."""
        with self._lock:
            n = self._conn.execute(
                "UPDATE jobs SET status='pending', attempts=0, next_attempt_at=0 "
                "WHERE status='failed'").rowcount
            self._conn.commit()
        if n:
            self._wake.set()
            logger.info("Spooler: %d job(s) 'failed' re-encolados manualmente", n)
        return n

    def _init_db(self):
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id          TEXT PRIMARY KEY,
                    printer_name    TEXT,
                    payload         TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    attempts        INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error      TEXT,
                    created_at      REAL NOT NULL,
                    updated_at      REAL NOT NULL
                )
            """)
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_pending "
                "ON jobs(status, next_attempt_at, created_at)")
            self._conn.commit()

    def enqueue(self, job_id, ticket, printer_name=None):
        """Persiste el trabajo. Devuelve True si es nuevo, False si era duplicado."""
        now = time.time()
        payload = json.dumps(ticket, ensure_ascii=False)
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO jobs "
                "(job_id, printer_name, payload, status, attempts, next_attempt_at, created_at, updated_at) "
                "VALUES (?,?,?,'pending',0,0,?,?)",
                (job_id, printer_name, payload, now, now))
            self._conn.commit()
            is_new = cur.rowcount > 0
        if is_new:
            self._wake.set()
            logger.info("Spooler: job %s encolado (impresora=%s)", job_id, printer_name)
        else:
            logger.info("Spooler: job %s DUPLICADO, ignorado (dedup)", job_id)
        return is_new

    def _claim_next(self):
        now = time.time()
        with self._lock:
            return self._conn.execute(
                "SELECT job_id, payload, attempts FROM jobs "
                "WHERE status='pending' AND next_attempt_at<=? "
                "ORDER BY created_at LIMIT 1", (now,)).fetchone()

    def _run(self):
        while not self._stop.is_set():
            row = self._claim_next()
            if row is None:
                self._wake.wait(timeout=self._idle_wait)
                self._wake.clear()
                continue
            job_id, payload, attempts = row
            try:
                ticket = json.loads(payload)
                self._print_fn(ticket)
                with self._lock:
                    self._conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
                    self._conn.commit()
                logger.info("Spooler: job %s impreso OK", job_id)
            except Exception as e:
                attempts += 1
                delay = min(self._base_delay * (2 ** min(attempts, 8)), self._max_delay)
                status = 'pending' if attempts < self._max_attempts else 'failed'
                with self._lock:
                    self._conn.execute(
                        "UPDATE jobs SET attempts=?, next_attempt_at=?, last_error=?, "
                        "status=?, updated_at=? WHERE job_id=?",
                        (attempts, time.time() + delay, str(e)[:500],
                         status, time.time(), job_id))
                    self._conn.commit()
                if status == 'failed':
                    logger.error("Spooler: job %s FALLÓ tras %d intentos (dead-letter): %s",
                                 job_id, attempts, e)
                else:
                    logger.warning("Spooler: job %s error (intento %d), reintenta en %.0fs: %s",
                                   job_id, attempts, delay, e)

    def pending_count(self):
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]

    def failed_count(self):
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='failed'").fetchone()[0]

    def stop(self):
        self._stop.set()
        self._wake.set()
