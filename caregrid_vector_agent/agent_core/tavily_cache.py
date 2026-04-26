"""
agent_core.tavily_cache — In-memory TTL cache for Tavily verification results.

Tavily searches are billable, slow, and (for the same facility) usually
return the same answer for hours. We therefore cache every successful
verification by *content key* so that repeated lookups inside one agent
run, or across runs sharing a Python process, never hit the API twice.

Public API
----------
- :class:`TavilyCache` — thread-safe in-memory cache with TTL.
- :func:`get_default_cache()` — module-level singleton used by
  :mod:`agent_core.tavily_verifier`.

Cache key
---------
The key is built deterministically from
``(facility_name, city, state, capabilities, depth)`` — see
:meth:`TavilyCache.make_key`. Capability lists are normalised
(lowercased, deduped, sorted) so that the order in which the agent
requests capabilities does not change the key.

TTL
---
Default 24 hours, configurable per cache instance. Expired entries are
lazily evicted on access — there is no background sweeper.

Backward compatibility
----------------------
The original file-based ``load_cache(facility_id)`` / ``save_cache(...)``
helpers are preserved for any external caller that might still rely on
them, but the verifier itself uses :class:`TavilyCache`.
"""

from __future__ import annotations

import json
import os
import time
from threading import Lock
from typing import Any, Iterable, Optional


# 24 hours in seconds.
DEFAULT_TTL_SECONDS: int = 24 * 60 * 60


class TavilyCache:
    """Simple thread-safe in-memory TTL cache for Tavily results."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._ttl: int = max(1, int(ttl_seconds))
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock: Lock = Lock()

    # ------------------------------------------------------------------
    # Key construction
    # ------------------------------------------------------------------
    @staticmethod
    def _norm(s: Any) -> str:
        return ("" if s is None else str(s)).strip().lower()

    @staticmethod
    def make_key(
        facility_name: Optional[str],
        city: Optional[str],
        state: Optional[str],
        capabilities: Optional[Iterable[str]],
        depth: Optional[str],
    ) -> str:
        """Build a deterministic cache key.

        The key is a single string so it survives JSON round-trips and is
        easy to log. Capability ordering is normalised so call sites need
        not pre-sort their lists.
        """
        name      = TavilyCache._norm(facility_name)
        city_n    = TavilyCache._norm(city)
        state_n   = TavilyCache._norm(state)
        depth_n   = TavilyCache._norm(depth)
        caps_iter = capabilities or []
        caps      = sorted({TavilyCache._norm(c) for c in caps_iter if TavilyCache._norm(c)})
        return (
            f"name={name}|city={city_n}|state={state_n}|"
            f"caps={','.join(caps)}|depth={depth_n}"
        )

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    def get(self, key: str) -> Optional[Any]:
        """Return the cached value or ``None`` if missing / expired."""
        if not key:
            return None
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            ts, value = entry
            if time.time() - ts > self._ttl:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        """Insert / overwrite an entry with the current timestamp."""
        if not key:
            return
        with self._lock:
            self._store[key] = (time.time(), value)

    def invalidate(self, key: str) -> None:
        """Remove a single entry; no-op if not present."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Empty the cache (mainly for tests)."""
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        """Number of live entries (does not run a sweep)."""
        with self._lock:
            return len(self._store)

    @property
    def ttl_seconds(self) -> int:
        return self._ttl


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_cache: TavilyCache = TavilyCache()


def get_default_cache() -> TavilyCache:
    """Return the process-wide default cache used by the verifier."""
    return _default_cache


def reset_default_cache(ttl_seconds: int = DEFAULT_TTL_SECONDS) -> TavilyCache:
    """Replace the singleton with a fresh cache (used by tests)."""
    global _default_cache
    _default_cache = TavilyCache(ttl_seconds=ttl_seconds)
    return _default_cache


# ---------------------------------------------------------------------------
# Backward-compatibility — file-based per-facility cache
# ---------------------------------------------------------------------------
# These functions predate the in-memory TTL cache and are preserved so any
# script that imports them keeps working. New code should use TavilyCache.
# ---------------------------------------------------------------------------

def load_cache(facility_id: str, cache_dir: str = "data/tavily_cache") -> dict | None:
    """Legacy: read a per-facility JSON file from disk (or ``None``)."""
    if not facility_id:
        return None
    path = os.path.join(cache_dir, f"{facility_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_cache(
    facility_id: str,
    result: dict,
    cache_dir: str = "data/tavily_cache",
) -> None:
    """Legacy: write a per-facility JSON file to disk."""
    if not facility_id:
        return
    try:
        os.makedirs(cache_dir, exist_ok=True)
        path = os.path.join(cache_dir, f"{facility_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    except OSError:
        # Cache failures must never crash the agent.
        return
