import json
import logging
import time

from fiscalberry.common.live_log_stream import LiveLogStreamManager


def _wait_until(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_stream_sends_snapshot_and_new_logs():
    manager = LiveLogStreamManager()
    published = []
    logger = logging.getLogger("test.live.snapshot")
    logger.setLevel(logging.DEBUG)

    logger.info("antes de abrir")
    assert manager.start_session(
        "session-1",
        "resto",
        "uuid-1",
        lambda topic, payload, qos: published.append((topic, json.loads(payload), qos)),
    )
    logger.warning("despues de abrir")

    assert _wait_until(lambda: len(published) >= 2)
    entries = [entry for _, batch, _ in published for entry in batch["entries"]]
    assert any(entry["message"] == "antes de abrir" for entry in entries)
    assert any(entry["message"] == "despues de abrir" for entry in entries)
    assert all(topic == "fiscalberry/logs/resto/uuid-1/session-1" for topic, _, _ in published)


def test_stream_stops_after_last_session():
    manager = LiveLogStreamManager()
    published = []
    logger = logging.getLogger("test.live.stop")
    logger.setLevel(logging.DEBUG)
    manager.start_session(
        "session-1",
        "resto",
        "uuid-1",
        lambda topic, payload, qos: published.append(payload),
        snapshot_lines=0,
    )
    published.clear()
    assert manager.stop_session("session-1") is True
    logger.error("no enviar")
    time.sleep(0.35)
    assert published == []


def test_stream_sanitizes_sensitive_values():
    manager = LiveLogStreamManager()
    published = []
    logger = logging.getLogger("test.live.sanitize")
    manager.start_session(
        "session-1",
        "resto",
        "uuid-1",
        lambda topic, payload, qos: published.append(json.loads(payload)),
        snapshot_lines=0,
    )
    logger.error("password=secreto token:abc123 normal=visible")

    assert _wait_until(lambda: any(batch["entries"] for batch in published))
    message = next(batch for batch in published if batch["entries"])["entries"][-1]["message"]
    assert "secreto" not in message
    assert "abc123" not in message
    assert "normal=visible" in message


def test_stream_expires_abandoned_session():
    manager = LiveLogStreamManager()
    manager.start_session(
        "session-1",
        "resto",
        "uuid-1",
        lambda topic, payload, qos: None,
        expires_at="2000-01-01T00:00:00+00:00",
        snapshot_lines=0,
    )
    assert _wait_until(lambda: manager.active_session_count() == 0)


def test_stream_applies_level_per_session():
    manager = LiveLogStreamManager()
    published = []
    publish = lambda topic, payload, qos: published.append(json.loads(payload))
    logger = logging.getLogger("test.live.levels")
    manager.start_session("debug", "resto", "uuid-1", publish, min_level="DEBUG", snapshot_lines=0)
    manager.start_session("error", "resto", "uuid-1", publish, min_level="ERROR", snapshot_lines=0)

    logger.info("solo debug")
    logger.error("ambos")

    assert _wait_until(
        lambda: sum(len(batch["entries"]) for batch in published) >= 3
    )
    by_session = {
        session_id: [
            entry
            for batch in published
            if batch["sessionIds"][0] == session_id
            for entry in batch["entries"]
        ]
        for session_id in ("debug", "error")
    }
    assert [entry["message"] for entry in by_session["debug"]] == ["solo debug", "ambos"]
    assert [entry["message"] for entry in by_session["error"]] == ["ambos"]


def test_stream_counts_failed_publish_as_dropped():
    manager = LiveLogStreamManager()
    published = []
    attempts = {"failed_entries": False}

    def publish(topic, payload, qos):
        batch = json.loads(payload)
        if batch["entries"] and not attempts["failed_entries"]:
            attempts["failed_entries"] = True
            return False
        published.append(batch)
        return True

    logger = logging.getLogger("test.live.publish_failure")
    manager.start_session("session-1", "resto", "uuid-1", publish, snapshot_lines=0)
    logger.error("se pierde")
    assert _wait_until(lambda: attempts["failed_entries"] is True)
    logger.error("siguiente")

    assert _wait_until(lambda: any(batch["droppedCount"] for batch in published))
    assert next(batch for batch in published if batch["droppedCount"])["droppedCount"] >= 1


def test_stream_accepts_null_snapshot_lines():
    manager = LiveLogStreamManager()
    published = []

    assert manager.start_session(
        "session-1",
        "resto",
        "uuid-1",
        lambda topic, payload, qos: published.append(json.loads(payload)),
        snapshot_lines=None,
    )
    assert published[0]["entries"] == []
