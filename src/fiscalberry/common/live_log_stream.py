import json
import logging
import queue
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone


SCHEMA_VERSION = 1
MAX_SNAPSHOT_LINES = 200
MAX_BUFFERED_LINES = 1000
MAX_BATCH_LINES = 50
MAX_MESSAGE_LENGTH = 8192
FLUSH_INTERVAL_SECONDS = 0.25
DEFAULT_LEASE_SECONDS = 90
# Tope del lease (mismo valor que paxa-core): aunque llegue un expiresAt lejano,
# el equipo deja de mandar logs si el panel no renueva.
MAX_LEASE_SECONDS = 600

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|authorization|api[_-]?key|rabbitmq_password)"
    r"(\s*[:=]\s*)([^\s,;}&]+)"
)


def _sanitize(value):
    text = str(value or "")[:MAX_MESSAGE_LENGTH]
    return _SENSITIVE_VALUE_RE.sub(r"\1\2***", text)


class _CaptureHandler(logging.Handler):
    def __init__(self, manager):
        super().__init__(level=logging.DEBUG)
        self._manager = manager
        # Sin formatter, `logger.exception(...)` llegaba al panel sin traceback.
        self.setFormatter(logging.Formatter())

    def emit(self, record):
        if record.name.startswith("fiscalberry.live_logs"):
            return
        try:
            exception = None
            if record.exc_info:
                exception = self.formatter.formatException(record.exc_info) if self.formatter else None
            self._manager.capture(
                {
                    "sequence": self._manager.next_sequence(),
                    "timestamp": datetime.fromtimestamp(
                        record.created, tz=timezone.utc
                    ).isoformat(),
                    "level": record.levelname,
                    "logger": record.name or "root",
                    "message": _sanitize(record.getMessage()),
                    "exception": _sanitize(exception) if exception else None,
                }
            )
        except Exception:
            self.handleError(record)


class LiveLogStreamManager:
    def __init__(self):
        self._history = deque(maxlen=MAX_SNAPSHOT_LINES)
        self._pending = queue.Queue(maxsize=MAX_BUFFERED_LINES)
        self._sessions = {}
        # Historial inicial de cada sesion nueva: lo publica el hilo del manager
        # (start_session corre en el hilo de Socket.IO y no debe bloquearlo).
        self._snapshots = queue.Queue()
        self._publisher = None
        self._on_idle = None
        self._tenant = ""
        self._uuid = ""
        self._sequence = 0
        self._dropped_count = 0
        self._previous_root_level = None
        self._lock = threading.RLock()
        self._handler = _CaptureHandler(self)
        self._worker = threading.Thread(
            target=self._run,
            name="fiscalberry-live-logs",
            daemon=True,
        )
        logging.getLogger().addHandler(self._handler)
        self._worker.start()

    def next_sequence(self):
        with self._lock:
            self._sequence += 1
            return self._sequence

    def capture(self, entry):
        with self._lock:
            self._history.append(entry)
            has_sessions = bool(self._sessions)
        if not has_sessions:
            return
        try:
            self._pending.put_nowait(entry)
        except queue.Full:
            with self._lock:
                self._dropped_count += 1

    def start_session(
        self,
        session_id,
        tenant,
        uuid,
        publisher,
        expires_at=None,
        min_level="DEBUG",
        snapshot_lines=MAX_SNAPSHOT_LINES,
        on_idle=None,
    ):
        """Abre (o reabre) una sesion de visualizacion.

        `publisher(topic, payload, qos) -> bool` publica un batch; `on_idle()` se
        llama (fuera del lock) cuando se cierra la ultima sesion, para liberar
        la conexion dedicada.
        """
        if not session_id or not tenant or not uuid or not callable(publisher):
            return False
        level = _LEVELS.get(str(min_level).upper(), logging.DEBUG)
        expires_epoch = self._expires_epoch(expires_at)
        try:
            snapshot_count = int(snapshot_lines)
        except (TypeError, ValueError):
            snapshot_count = MAX_SNAPSHOT_LINES
        with self._lock:
            first_session = not self._sessions
            self._sessions[session_id] = {
                "expires_at": expires_epoch,
                "min_level": level,
                "started_sequence": self._sequence,
            }
            self._publisher = publisher
            self._on_idle = on_idle
            self._tenant = tenant
            self._uuid = uuid
            if first_session:
                root = logging.getLogger()
                self._previous_root_level = root.level
                root.setLevel(logging.DEBUG)
            snapshot = list(self._history)[
                -max(0, min(snapshot_count, MAX_SNAPSHOT_LINES)) :
            ]
            snapshot = [
                entry
                for entry in snapshot
                if _LEVELS.get(entry["level"], logging.INFO) >= level
            ]
            # Se publica aunque este vacio: es la confirmacion que espera el panel.
            self._snapshots.put((session_id, snapshot))
        return True

    def renew_session(self, session_id, expires_at=None):
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session["expires_at"] = self._expires_epoch(expires_at)
            return True

    def stop_session(self, session_id):
        with self._lock:
            removed = self._sessions.pop(session_id, None) is not None
            on_idle = self._restore_level_if_idle()
        self._call_on_idle(on_idle)
        return removed

    def active_session_count(self):
        with self._lock:
            return len(self._sessions)

    def stop_all_sessions(self):
        with self._lock:
            self._sessions.clear()
            on_idle = self._restore_level_if_idle()
        self._call_on_idle(on_idle)

    def _expires_epoch(self, expires_at):
        now = time.time()
        if expires_at:
            try:
                parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return min(parsed.timestamp(), now + MAX_LEASE_SECONDS)
            except (TypeError, ValueError):
                pass
        return now + DEFAULT_LEASE_SECONDS

    def _expire_sessions(self):
        now = time.time()
        with self._lock:
            expired = [
                session_id
                for session_id, session in self._sessions.items()
                if session["expires_at"] <= now
            ]
            for session_id in expired:
                self._sessions.pop(session_id, None)
            on_idle = self._restore_level_if_idle()
        self._call_on_idle(on_idle)

    def _restore_level_if_idle(self):
        """Sin sesiones: restaura el nivel y devuelve el `on_idle` a llamar (bajo lock)."""
        if self._sessions or self._previous_root_level is None:
            return None
        logging.getLogger().setLevel(self._previous_root_level)
        self._previous_root_level = None
        self._publisher = None
        on_idle = self._on_idle
        self._on_idle = None
        self._tenant = ""
        self._uuid = ""
        # Las perdidas son de las sesiones que se cerraron: la proxima no las hereda.
        self._dropped_count = 0

        for pending in (self._pending, self._snapshots):
            while True:
                try:
                    pending.get_nowait()
                except queue.Empty:
                    break
        return on_idle

    @staticmethod
    def _call_on_idle(on_idle):
        if on_idle is None:
            return
        try:
            on_idle()
        except Exception:  # noqa: BLE001 - cerrar la conexion nunca debe romper al caller
            pass

    def _flush_snapshots(self):
        while True:
            try:
                session_id, entries = self._snapshots.get_nowait()
            except queue.Empty:
                return
            with self._lock:
                active = session_id in self._sessions
            if active:
                self._publish(entries, [session_id], dropped_count=0)

    def _run(self):
        while True:
            self._expire_sessions()
            self._flush_snapshots()
            try:
                first = self._pending.get(timeout=FLUSH_INTERVAL_SECONDS)
            except queue.Empty:
                continue
            batch = [first]
            deadline = time.monotonic() + FLUSH_INTERVAL_SECONDS
            while len(batch) < MAX_BATCH_LINES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(self._pending.get(timeout=remaining))
                except queue.Empty:
                    break
            # Una sesion abierta mientras se juntaba el batch manda primero su
            # historial: el panel recibe las lineas en orden.
            self._flush_snapshots()
            with self._lock:
                sessions = dict(self._sessions)
                dropped_count = self._dropped_count
                self._dropped_count = 0
            if not sessions:
                continue
            for session_id, session in sessions.items():
                filtered = [
                    entry
                    for entry in batch
                    if entry["sequence"] > session["started_sequence"]
                    and _LEVELS.get(entry["level"], logging.INFO) >= session["min_level"]
                ]
                if filtered or dropped_count:
                    self._publish(filtered, [session_id], dropped_count)

    def _publish(self, entries, session_ids, dropped_count):
        with self._lock:
            publisher = self._publisher
            tenant = self._tenant
            uuid = self._uuid
        if not publisher or not tenant or not uuid:
            return
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "sessionIds": session_ids,
            "uuid": uuid,
            "tenant": tenant,
            "entries": entries,
            "droppedCount": dropped_count,
        }
        try:
            published = publisher(
                "fiscalberry/logs/{}/{}/{}".format(tenant, uuid, session_ids[0]),
                json.dumps(payload, ensure_ascii=False),
                0,
            )
            if published is False:
                with self._lock:
                    self._dropped_count += len(entries)
        except Exception:
            with self._lock:
                self._dropped_count += len(entries)


_manager = None
_manager_lock = threading.Lock()


def get_live_log_stream_manager():
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = LiveLogStreamManager()
        return _manager


def install_live_log_capture():
    return get_live_log_stream_manager()
