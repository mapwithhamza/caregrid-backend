"""Backend integration adapter for the standalone CareGrid Vector Agent.

This module is the **only** place the FastAPI backend imports the
standalone agent (`caregrid_vector_agent/agent_core/...`). It:

1. Bootstraps `sys.path` so the standalone package is importable when
   the backend is launched from anywhere (uvicorn, run.py, pytest).
2. Lazily imports `agent_core.recommendation_engine.run_recommendation`
   the first time it is called — so the backend boots cleanly even if
   the standalone agent has a transient import problem.
3. Calls the agent with the dataframe the backend already loaded
   (no second CSV read, no second copy on disk).
4. Converts the agent's Pydantic `AgentResponse` into a JSON-safe dict
   (NaN → None, numpy → Python primitives) for direct return from a
   FastAPI route.
5. Never raises. On any failure (import, signature mismatch, runtime),
   it returns ``(None, "<short safe error>")`` so the caller can fall
   back to the simple legacy recommender.

The standalone agent is a *pure function* under the hood: same query +
same dataframe ⇒ same answer. Vector search and Tavily verification are
opt-in and read their own settings from the process environment via
`pydantic-settings` — the backend never sees the secrets.
"""

from __future__ import annotations

import logging
import math
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Path bootstrap — make the standalone agent importable
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_AGENT_ROOT = _BACKEND_ROOT / "caregrid_vector_agent"

if _AGENT_ROOT.exists() and str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


_run_recommendation = None  # type: ignore[var-annotated]
_run_recommendation_lock = threading.Lock()
_run_recommendation_error: Optional[str] = None


def _lazy_import_run_recommendation():
    """Import the standalone agent the first time it's needed.

    Returns the callable, or ``None`` if the import failed. Caches both
    success and failure so a broken environment never re-pays the
    import cost on every request.
    """
    global _run_recommendation, _run_recommendation_error

    if _run_recommendation is not None or _run_recommendation_error is not None:
        return _run_recommendation

    with _run_recommendation_lock:
        if _run_recommendation is not None or _run_recommendation_error is not None:
            return _run_recommendation

        try:
            from agent_core.recommendation_engine import (
                run_recommendation,
            )

            _run_recommendation = run_recommendation
            logger.info(
                "Standalone CareGrid agent imported successfully from %s",
                _AGENT_ROOT,
            )
        except Exception as exc:  # noqa: BLE001
            _run_recommendation_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Standalone CareGrid agent import failed (%s); the backend "
                "will use the legacy simple recommender.",
                _run_recommendation_error,
            )
            _run_recommendation = None

    return _run_recommendation


# ---------------------------------------------------------------------------
# 2. JSON-safety helpers
# ---------------------------------------------------------------------------


def _is_nan(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float):
        return math.isnan(value)
    try:
        import numpy as np  # local import — numpy may not be present in some test envs

        if isinstance(value, np.floating):
            return bool(np.isnan(value))
    except Exception:  # noqa: BLE001
        return False
    return False


def _make_json_safe(value: Any) -> Any:
    """Recursively convert pandas/numpy/NaN scalars into JSON-safe Python."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _make_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_make_json_safe(v) for v in value]

    try:
        import numpy as np

        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return None if np.isnan(value) else float(value)
    except Exception:  # noqa: BLE001
        pass

    if isinstance(value, float) and math.isnan(value):
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:  # noqa: BLE001
        pass

    return value


def _response_to_dict(response: Any) -> dict[str, Any]:
    """Convert the standalone agent's ``AgentResponse`` into a JSON-safe dict.

    Supports both Pydantic v2 (``model_dump``) and v1 (``dict``)
    response objects. Falls back to ``vars()`` for plain dataclass-ish
    fallback objects.
    """
    if response is None:
        return {}
    if hasattr(response, "model_dump"):
        try:
            payload = response.model_dump(mode="json", by_alias=False, exclude_none=False)
        except Exception:  # noqa: BLE001
            payload = response.model_dump()
    elif hasattr(response, "dict"):
        payload = response.dict()
    else:
        payload = dict(getattr(response, "__dict__", {}))
    return _make_json_safe(payload)


# ---------------------------------------------------------------------------
# 3. Public entry point
# ---------------------------------------------------------------------------


def is_available() -> bool:
    """Return True if the standalone agent imported cleanly."""
    return _lazy_import_run_recommendation() is not None


def import_error() -> Optional[str]:
    """Return the last import-time error string, or None if everything imported cleanly."""
    _lazy_import_run_recommendation()
    return _run_recommendation_error


def run_advanced_recommendation(
    *,
    query: str,
    facilities_df: pd.DataFrame,
    state: Optional[str] = None,
    facility_type: Optional[str] = None,
    min_trust_score: Optional[float] = None,
    max_results: int = 5,
    enable_vector_search: bool = False,
    enable_web_verification: bool = False,
    web_verification_depth: str = "basic",
    max_web_verified: int = 2,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Call the standalone agent and return ``(payload_dict, error)``.

    * ``payload_dict`` is a JSON-safe dict ready to ship to the
      frontend. ``None`` means the call failed and the caller should
      fall back to the legacy simple recommender.
    * ``error`` is a short, secret-free error string (or ``None`` on
      success). The caller is expected to log it server-side and
      surface it inside ``trace_summary.errors`` on the fallback
      response.

    Never raises. Vector and Tavily are read-from-env opt-ins; if
    either credential is missing the agent's own graceful-degradation
    contract handles it (`vector_available=false` / verification
    `skipped`).
    """
    runner = _lazy_import_run_recommendation()
    if runner is None:
        return None, _run_recommendation_error or "agent_import_failed"

    if facilities_df is None or len(facilities_df) == 0:
        return None, "facilities_dataframe_empty"

    try:
        response = runner(
            query=query,
            facilities_df=facilities_df,
            state=state,
            facility_type=facility_type,
            min_trust_score=min_trust_score,
            max_results=max_results,
            enable_vector_search=bool(enable_vector_search),
            enable_web_verification=bool(enable_web_verification),
            web_verification_depth=str(web_verification_depth or "basic"),
            max_web_verified=int(max_web_verified or 2),
        )
    except TypeError as exc:
        # Defensive: future signature drift shouldn't take the API down.
        logger.warning("Advanced agent signature mismatch (%s) — falling back.", exc)
        return None, f"agent_signature_error: {exc}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Advanced agent call failed; falling back to simple recommender.")
        return None, f"agent_runtime_error: {type(exc).__name__}: {exc}"

    try:
        payload = _response_to_dict(response)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Advanced agent response serialisation failed; falling back.")
        return None, f"agent_serialise_error: {type(exc).__name__}: {exc}"

    return payload, None
