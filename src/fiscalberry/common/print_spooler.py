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
            # journal_mode=WAL por si solo deja synchronous en NORMAL (default de
            # SQLite en WAL). Con NORMAL el commit NO hace fsync del WAL -> ante un
            # corte de energia o un OS crash se puede perder TODO lo escrito desde
            # el ultimo checkpoint, no solo la ultima transaccion (issue #165: la
            # tabla quedaba vacia tras un power-cycle). FULL fuerza fsync del
            # WAL en cada commit: la garantia de "nunca perder impresiones" no
            # puede depender de un cierre ordenado del proceso.
            self._conn.execute("PRAGMA synchronous=FULL")
        except Exception:
            pass
        self._init_db()
        self._recover_on_start()
        # Debe existir ANTES de arrancar el worker: _run() lo lee desde su
        # primer ciclo si la cola arranca vacía (race si se setea después).
        self._last_pending_log = time.time()
        self._worker = threading.Thread(target=self._run, name="print-spooler", daemon=True)
        self._worker.start()
        pending, failed = self.pending_count(), self.failed_count()
        logger.info("Spooler durable iniciado (db=%s)", self._db_path)
        # Visibilidad al arrancar (issue #166): antes una perdida o una cola
        # acumulada eran invisibles hasta que alguien notaba que faltaban
        # comprobantes. Este log es el "aviso" minimo que cubre tambien el
        # camino headless (CLI/Raspberry, sin GUI).
        if pending or failed:
            logger.warning(
                "Spooler: hay trabajos sin imprimir de una sesion anterior "
                "(pending=%d, failed=%d)", pending, failed)

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

    def discard_all(self):
        """Descarta TODA la cola ('pending' + 'failed'). Devuelve cuántos.

        Acción "descartar" de la issue #166: el operador decide explícitamente
        no imprimir lo acumulado (ej. impresora fue reemplazada, comandas ya
        vencidas). No toca la dedup: si más tarde llega un job con el mismo
        job_id ya descartado, se vuelve a aceptar (se descartó a propósito).
        """
        with self._lock:
            n = self._conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('pending','failed')"
            ).fetchone()[0]
            self._conn.execute(
                "DELETE FROM jobs WHERE status IN ('pending','failed')")
            self._conn.commit()
        if n:
            # WARNING a propósito: se están descartando comprobantes fiscales
            # y comandas, no una notificación cualquiera. Tiene que quedar
            # rastro en el log de quien lo pidió y cuándo.
            logger.warning("Spooler: %d job(s) DESCARTADOS manualmente (no se imprimirán)", n)
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
                self._maybe_log_pending()
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
                    # Checkpoint PASSIVE (no bloquea lectores/escritores, aporta lo
                    # que puede): con synchronous=FULL cada commit ya es durable,
                    # esto es solo para no dejar el WAL creciendo indefinidamente
                    # con el volumen bajo de este spooler (issue #165, propuesta 2).
                    try:
                        self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                    except Exception:
                        pass
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

    # Cada cuánto se repite el aviso de cola estancada mientras el worker está
    # ocioso (issue #166: "loguear el pendiente ... cuando supere un umbral").
    # El umbral es simplemente >0: cualquier trabajo sin imprimir es visible.
    _PENDING_LOG_INTERVAL = 300.0

    def _maybe_log_pending(self):
        """Avisa periódicamente si hay trabajos estancados (worker ocioso).

        Se llama solo cuando `_claim_next()` no encontró nada para imprimir
        AHORA: o la cola está vacía, o todo lo pendiente está esperando su
        backoff. En el segundo caso, sin este log, una impresora caída mucho
        tiempo es tan invisible como la pérdida original de la #165.
        """
        now = time.time()
        if now - self._last_pending_log < self._PENDING_LOG_INTERVAL:
            return
        self._last_pending_log = now
        pending, failed = self.pending_count(), self.failed_count()
        if pending or failed:
            logger.warning(
                "Spooler: cola sin drenar (pending=%d, failed=%d)", pending, failed)

    def pending_count(self):
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]

    def failed_count(self):
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='failed'").fetchone()[0]

    def stop(self, timeout=5.0):
        """Cierre ordenado: para el worker, hace checkpoint y cierra la conexión.

        Antes stop() solo señalizaba (el `os._exit()` del proceso servicio
        mataba todo sin tocar el spooler). Con PRAGMA synchronous=FULL el
        contrato de durabilidad ya no depende de esto, pero cerrar bien evita
        dejar el WAL creciendo y conexiones sqlite a medio commit (issue #165,
        propuesta 3).
        """
        self._stop.set()
        self._wake.set()
        if self._worker.is_alive():
            self._worker.join(timeout=timeout)
        with self._lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
