"""
agent_core.audit_logger — Append-only audit log for agent decisions.

Every interesting event in the recommendation pipeline (intent parsed,
local retrieval done, vector search attempted, validation findings,
Tavily verification, final response) is recorded as a structured event.

Two modes are supported:

1. **In-memory only** — events live on the :class:`AuditLogger`
   instance and are discarded when the process ends. Use this in tests
   and short-lived scripts.

2. **In-memory + JSONL file** — events are also appended one line per
   event to a JSONL file (default ``data/outputs/audit_log.jsonl``).
   File-IO errors are swallowed so the agent never crashes because of
   logging.

The original module-level :func:`log_event` is preserved for backward
compatibility with anything that was already calling it.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional


DEFAULT_LOG_PATH: str = "data/outputs/audit_log.jsonl"


def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: str, event: dict) -> None:
    """Append a single JSON-serialisable event to a JSONL file."""
    if not path:
        return
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


class AuditLogger:
    """In-memory + optional JSONL file audit log.

    Parameters
    ----------
    log_path:
        File to append events to. Defaults to
        :data:`DEFAULT_LOG_PATH`. Pass ``None`` (or set ``persist=False``)
        to keep events in memory only.
    persist:
        If False, events are kept in-memory but never written to disk.
        Useful for tests.
    settings:
        Optional settings object; if provided and has ``audit_log_path``
        attribute, that value is used (unless overridden by
        ``log_path``).
    """

    def __init__(
        self,
        log_path: Optional[str] = None,
        *,
        persist: bool = True,
        settings: Any = None,
    ) -> None:
        if log_path is None and settings is not None:
            log_path = getattr(settings, "audit_log_path", None)
        self.log_path: Optional[str] = log_path or DEFAULT_LOG_PATH
        self.persist: bool = bool(persist)
        self._events: list[dict] = []
        self._lock: Lock = Lock()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------
    def log(
        self,
        event_type: str,
        payload: Optional[dict] = None,
        *,
        persist: Optional[bool] = None,
    ) -> dict:
        """Record one event.

        Parameters
        ----------
        event_type:
            Stable string id, e.g. ``"intent_parsed"`` /
            ``"local_retrieval"`` / ``"final_response"``.
        payload:
            Arbitrary JSON-serialisable dict. ``None`` is treated as
            empty.
        persist:
            Per-call override of the instance's ``persist`` flag.

        Returns
        -------
        dict
            The recorded event (so callers can also inspect it).
        """
        evt = {
            "event_type": str(event_type),
            "timestamp": _now_iso(),
            "payload": payload or {},
        }
        with self._lock:
            self._events.append(evt)
            should_persist = self.persist if persist is None else bool(persist)
            if should_persist and self.log_path:
                try:
                    _append_jsonl(self.log_path, evt)
                except OSError:
                    # Logging failures must never propagate.
                    pass
        return evt

    def get_events(self) -> list[dict]:
        """Return a *copy* of the in-memory event list."""
        with self._lock:
            return [dict(e) for e in self._events]

    def event_types(self) -> list[str]:
        """List of event-type strings in the order they were logged."""
        with self._lock:
            return [e["event_type"] for e in self._events]

    def to_summary(self) -> dict:
        """Aggregate summary suitable for embedding in ``trace_summary``."""
        with self._lock:
            counts = Counter(e["event_type"] for e in self._events)
            return {
                "total_events": len(self._events),
                "event_type_counts": dict(counts),
                "first_event_at": self._events[0]["timestamp"] if self._events else None,
                "last_event_at": self._events[-1]["timestamp"] if self._events else None,
            }

    def clear(self) -> None:
        """Clear in-memory events (does not touch the file)."""
        with self._lock:
            self._events.clear()

    def __len__(self) -> int:  # convenience
        with self._lock:
            return len(self._events)


# ---------------------------------------------------------------------------
# Module-level singleton & backward-compat function
# ---------------------------------------------------------------------------

_default_logger: AuditLogger = AuditLogger(persist=False)


def get_default_audit_logger() -> AuditLogger:
    """Process-wide default logger (persist=False until reset)."""
    return _default_logger


def reset_default_audit_logger(
    log_path: Optional[str] = None,
    *,
    persist: bool = True,
) -> AuditLogger:
    """Replace the singleton (used by tests and integration code)."""
    global _default_logger
    _default_logger = AuditLogger(log_path=log_path, persist=persist)
    return _default_logger


def log_event(event: dict, log_path: str = DEFAULT_LOG_PATH) -> None:
    """Backward-compat: append a single event dict to ``log_path``.

    Failures are swallowed so legacy callers cannot bring the agent down.
    """
    try:
        evt = dict(event or {})
        evt["_logged_at"] = _now_iso()
        _append_jsonl(log_path, evt)
    except OSError:
        return
