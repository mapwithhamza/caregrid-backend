"""
agent_core.tavily_verifier — Optional external web verification via Tavily.

Tavily is an *optional* layer. When disabled (the default), the agent
must run end-to-end without contacting any external service. When
enabled, the verifier performs one or two web searches per facility and
scores how well the public web evidence agrees with what the dataset
claims.

Public API
----------
- :func:`verify_facility_web_presence(facility_name, city, state,
  requested_capabilities=None, depth="basic")` — verify a single
  facility. Always returns a :class:`WebVerificationResult`; never
  raises.

- :func:`verify_top_recommendations(recommendations, max_to_verify=3,
  depth="basic")` — verify up to ``max_to_verify`` recommendations and
  return one :class:`WebVerificationResult` per verified item.

Depth modes
-----------
``basic``     — one Tavily search (``"{name} {city} {state}"``).
``advanced``  — basic + a second capability-aware search
                (``"{name} {city} {capabilities}"``).
``demo``      — advanced + best-effort extraction of an "official-looking"
                URL (filters out aggregator domains like JustDial, Practo).

Failure modes (verification_status)
-----------------------------------
``skipped``    — Tavily disabled or API key missing. No call attempted.
``error``      — Call attempted but failed. ``error_message`` populated.
``unverified`` — Call succeeded but the public web didn't agree.
``partial``    — Some signal (name OR location), score in ``[0.4, 0.7)``.
``verified``   — Strong signal (name + location), score >= 0.7.

The verifier never raises. Cache hits are returned with ``cached=True``.
The Tavily SDK is imported lazily inside :func:`_default_client_factory`
so that the rest of the agent can run with ``tavily-python`` uninstalled.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from agent_core.schemas import WebVerificationResult
from agent_core.tavily_cache import TavilyCache, get_default_cache


# ---------------------------------------------------------------------------
# Status / reason / depth constants — exported for tests and integrators
# ---------------------------------------------------------------------------

VERIFICATION_VERIFIED   = "verified"
VERIFICATION_PARTIAL    = "partial"
VERIFICATION_UNVERIFIED = "unverified"
VERIFICATION_SKIPPED    = "skipped"
VERIFICATION_ERROR      = "error"

REASON_DISABLED         = "tavily_disabled"
REASON_MISSING_KEY      = "missing_tavily_api_key"
REASON_SDK_UNAVAILABLE  = "tavily_sdk_unavailable"
REASON_API_ERROR        = "tavily_api_error"

DEPTH_BASIC    = "basic"
DEPTH_ADVANCED = "advanced"
DEPTH_DEMO     = "demo"
ALLOWED_DEPTHS = {DEPTH_BASIC, DEPTH_ADVANCED, DEPTH_DEMO}


# Aggregator / non-official domains we down-weight when picking an
# "official-looking" URL in demo depth.
_AGGREGATOR_DOMAINS: set[str] = {
    "justdial.com",
    "sulekha.com",
    "practo.com",
    "lybrate.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "wikipedia.org",
    "wikidata.org",
    "youtube.com",
    "yelp.com",
    "tripadvisor.com",
    "google.com",
    "maps.google.com",
}

# Hard caps so a misbehaving Tavily response cannot blow up logs.
_MAX_SOURCES_KEPT  = 5
_MAX_NOTES_LEN     = 12
_MAX_SUMMARY_CHARS = 500
_MAX_SNIPPET_CHARS = 280
_MAX_ERROR_CHARS   = 200


# ---------------------------------------------------------------------------
# Settings access — lazy so tests don't need .env
# ---------------------------------------------------------------------------

def _import_settings() -> Any:
    """Import the settings singleton lazily (avoids import-time cost in tests)."""
    from config.settings import settings  # noqa: WPS433  (deliberate lazy import)
    return settings


def _default_client_factory(api_key: str) -> Any:
    """Default Tavily client factory; imported lazily.

    Tests inject their own ``client_factory`` so the real SDK is never
    needed. The verifier itself only requires ``client.search(query=...,
    search_depth=..., max_results=...)``.
    """
    from tavily import TavilyClient  # noqa: WPS433  (deliberate lazy import)
    return TavilyClient(api_key=api_key)


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------

def _short_error(exc: BaseException) -> str:
    """Render an exception as a single short, log-safe line."""
    msg = f"{type(exc).__name__}: {exc}"
    msg = msg.replace("\n", " ").replace("\r", " ").strip()
    return msg[:_MAX_ERROR_CHARS]


def _skipped_result(
    *,
    facility_id: str,
    facility_name: str,
    reason_code: str,
    note: str,
    credits: int = 0,
) -> WebVerificationResult:
    return WebVerificationResult(
        facility_id=facility_id or facility_name or "",
        query_used="",
        verified=False,
        sources=[],
        summary="",
        cached=False,
        web_checked=False,
        web_available=False,
        matched_name="",
        matched_location="",
        matched_capability=[],
        top_url="",
        top_snippet="",
        verification_score=0.0,
        verification_status=VERIFICATION_SKIPPED,
        verification_notes=[reason_code, note] if note else [reason_code],
        error_message=None,
        credits_estimated=credits,
    )


def _error_result(
    *,
    facility_id: str,
    facility_name: str,
    reason_code: str,
    error_message: str,
    query_used: str = "",
    credits: int = 0,
) -> WebVerificationResult:
    return WebVerificationResult(
        facility_id=facility_id or facility_name or "",
        query_used=query_used,
        verified=False,
        sources=[],
        summary="",
        cached=False,
        web_checked=True,
        web_available=False,
        matched_name="",
        matched_location="",
        matched_capability=[],
        top_url="",
        top_snippet="",
        verification_score=0.0,
        verification_status=VERIFICATION_ERROR,
        verification_notes=[reason_code],
        error_message=error_message,
        credits_estimated=credits,
    )


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------

def _build_facility_query(
    facility_name: str,
    city: Optional[str],
    state: Optional[str],
) -> str:
    parts = [p for p in [facility_name, city, state] if p and str(p).strip()]
    return " ".join(str(p).strip() for p in parts)


def _build_capability_query(
    facility_name: str,
    city: Optional[str],
    state: Optional[str],
    capabilities: Optional[list[str]],
) -> str:
    cap_list = [c.strip() for c in (capabilities or []) if c and c.strip()]
    if not cap_list:
        return ""
    base = _build_facility_query(facility_name, city, state)
    cap_str = " ".join(cap_list[:6])
    return f"{base} {cap_str}".strip()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _normalise_capabilities(caps: Optional[list[str]]) -> list[str]:
    """Lowercase, strip, drop blanks; preserve input order without dupes."""
    seen: set[str] = set()
    out: list[str] = []
    for c in (caps or []):
        cn = (c or "").strip().lower()
        if cn and cn not in seen:
            seen.add(cn)
            out.append(cn)
    return out


def _find_official_url(urls: list[str], facility_name: str) -> Optional[str]:
    """Best-effort: return a URL that looks like the facility's own site.

    Heuristic: skip aggregator domains, prefer hosts whose name overlaps
    with a slug of ``facility_name``. Falls back to the first non-
    aggregator URL.
    """
    if not urls:
        return None
    name_slug = re.sub(r"[^a-z0-9]", "", (facility_name or "").lower())
    short_slug = name_slug[:6] if len(name_slug) >= 6 else name_slug
    fallback: Optional[str] = None
    for url in urls:
        host = (urlparse(url).netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not host:
            continue
        if any(host == d or host.endswith("." + d) for d in _AGGREGATOR_DOMAINS):
            continue
        if fallback is None:
            fallback = url
        if short_slug and short_slug in host.replace(".", "").replace("-", ""):
            return url
    return fallback


def _score_results(
    *,
    facility_id: str,
    facility_name: str,
    city: Optional[str],
    state: Optional[str],
    capabilities: Optional[list[str]],
    depth: str,
    results: list[dict],
    queries: list[str],
    credits: int,
) -> WebVerificationResult:
    """Translate Tavily search results into a scored WebVerificationResult."""
    name_lower  = (facility_name or "").lower().strip()
    city_lower  = (city or "").lower().strip()
    state_lower = (state or "").lower().strip()
    cap_terms   = _normalise_capabilities(capabilities)

    if not results:
        return WebVerificationResult(
            facility_id=facility_id or facility_name or "",
            query_used=queries[0] if queries else "",
            verified=False,
            sources=[],
            summary="",
            cached=False,
            web_checked=True,
            web_available=True,
            matched_name="",
            matched_location="",
            matched_capability=[],
            top_url="",
            top_snippet="",
            verification_score=0.0,
            verification_status=VERIFICATION_UNVERIFIED,
            verification_notes=["No matching results returned by Tavily."],
            error_message=None,
            credits_estimated=credits,
        )

    sources: list[str] = []
    matched_caps: list[str] = []
    notes: list[str] = []
    name_hit = city_hit = state_hit = False

    for r in results[:_MAX_SOURCES_KEPT]:
        url = (r.get("url") or "").strip()
        if url and url not in sources:
            sources.append(url)
        text = ((r.get("title") or "") + " " + (r.get("content") or "")).lower()
        if name_lower and name_lower in text:
            name_hit = True
        if city_lower and city_lower in text:
            city_hit = True
        if state_lower and state_lower in text:
            state_hit = True
        for cap in cap_terms:
            if cap and cap in text and cap not in matched_caps:
                matched_caps.append(cap)

    score = 0.0
    if name_hit:
        score += 0.4
    if city_hit:
        score += 0.2
    if state_hit:
        score += 0.1
    if matched_caps and cap_terms:
        score += 0.2 * min(1.0, len(matched_caps) / len(cap_terms))

    top = results[0] or {}
    top_url = (top.get("url") or "").strip()

    if depth == DEPTH_DEMO:
        official = _find_official_url(sources, facility_name)
        if official:
            top_url = official
            score += 0.1
            notes.append(f"Official-looking URL: {official}")

    score = max(0.0, min(1.0, score))

    if score >= 0.7:
        status = VERIFICATION_VERIFIED
    elif score >= 0.4:
        status = VERIFICATION_PARTIAL
    else:
        status = VERIFICATION_UNVERIFIED

    if name_hit:
        notes.append(f"Name match: {facility_name}")
    if city_hit:
        notes.append(f"City match: {city}")
    if state_hit:
        notes.append(f"State match: {state}")
    if matched_caps:
        notes.append(f"Capabilities matched: {sorted(matched_caps)}")
    notes = notes[:_MAX_NOTES_LEN]

    matched_location_parts = [
        p for p in [
            (city if city_hit else None),
            (state if state_hit else None),
        ] if p and str(p).strip()
    ]
    matched_location = ", ".join(str(p).strip() for p in matched_location_parts)

    return WebVerificationResult(
        facility_id=facility_id or facility_name or "",
        query_used=queries[0] if queries else "",
        verified=(status == VERIFICATION_VERIFIED),
        sources=sources[:_MAX_SOURCES_KEPT],
        summary=(top.get("content") or "")[:_MAX_SUMMARY_CHARS],
        cached=False,
        web_checked=True,
        web_available=True,
        matched_name=(facility_name if name_hit else ""),
        matched_location=matched_location,
        matched_capability=sorted(matched_caps),
        top_url=top_url,
        top_snippet=(top.get("content") or "")[:_MAX_SNIPPET_CHARS],
        verification_score=round(score, 3),
        verification_status=status,
        verification_notes=notes,
        error_message=None,
        credits_estimated=credits,
    )


# ---------------------------------------------------------------------------
# Public API: single-facility verification
# ---------------------------------------------------------------------------

def verify_facility_web_presence(
    facility_name: str,
    city: Optional[str] = None,
    state: Optional[str] = None,
    requested_capabilities: Optional[list[str]] = None,
    depth: str = DEPTH_BASIC,
    *,
    facility_id: Optional[str] = None,
    settings: Any = None,
    cache: Optional[TavilyCache] = None,
    client_factory: Optional[Callable[[str], Any]] = None,
) -> WebVerificationResult:
    """Verify a single facility against Tavily's public-web index.

    Parameters
    ----------
    facility_name :
        Display name of the facility (e.g. ``"Apollo Hospitals Mumbai"``).
    city, state :
        Location strings to bias the search and score the match. Either
        may be ``None``.
    requested_capabilities :
        Optional list of capability tokens (taxonomy IDs or human names)
        that the agent has claimed for this facility. Used in
        ``advanced`` / ``demo`` depth and in scoring.
    depth :
        ``"basic"`` (default), ``"advanced"``, or ``"demo"``. Unknown
        values fall back to ``"basic"``.
    facility_id :
        Optional canonical ID; defaults to ``facility_name``. The
        returned ``WebVerificationResult.facility_id`` is set from this.
    settings :
        Optional settings object (defaults to ``config.settings.settings``).
    cache :
        Optional :class:`TavilyCache` (defaults to the module singleton).
    client_factory :
        Optional callable ``(api_key) -> tavily-like client``. Tests inject
        a mock here so the real SDK is never imported.

    Returns
    -------
    WebVerificationResult
        Always — failures are reported via ``verification_status`` and
        ``error_message``.
    """
    s = settings if settings is not None else _import_settings()
    cache = cache if cache is not None else get_default_cache()
    facility_id_resolved = (facility_id or facility_name or "").strip()
    if depth not in ALLOWED_DEPTHS:
        depth = DEPTH_BASIC

    if not getattr(s, "tavily_enabled", False):
        return _skipped_result(
            facility_id=facility_id_resolved,
            facility_name=facility_name,
            reason_code=REASON_DISABLED,
            note="Tavily is disabled (TAVILY_ENABLED=false).",
        )

    api_key = (getattr(s, "tavily_api_key", None) or "").strip()
    if not api_key:
        return _skipped_result(
            facility_id=facility_id_resolved,
            facility_name=facility_name,
            reason_code=REASON_MISSING_KEY,
            note="TAVILY_API_KEY not set; cannot call Tavily.",
        )

    cache_key = TavilyCache.make_key(
        facility_name, city, state, requested_capabilities, depth,
    )
    cached_result = cache.get(cache_key)
    if isinstance(cached_result, WebVerificationResult):
        # Override facility_id with the caller's value: the cache key is
        # (name, city, state, caps, depth) — different callers may carry
        # different canonical facility_ids for the same external facility.
        # Without this override, downstream mapping by facility_id breaks.
        return cached_result.model_copy(
            update={"cached": True, "facility_id": facility_id_resolved}
        )

    factory = client_factory or _default_client_factory
    try:
        client = factory(api_key)
    except ImportError as exc:
        return _error_result(
            facility_id=facility_id_resolved,
            facility_name=facility_name,
            reason_code=REASON_SDK_UNAVAILABLE,
            error_message=_short_error(exc),
        )
    except Exception as exc:  # noqa: BLE001 (graceful degradation)
        return _error_result(
            facility_id=facility_id_resolved,
            facility_name=facility_name,
            reason_code=REASON_API_ERROR,
            error_message=_short_error(exc),
        )

    queries: list[str] = [_build_facility_query(facility_name, city, state)]
    if depth in (DEPTH_ADVANCED, DEPTH_DEMO):
        cap_query = _build_capability_query(
            facility_name, city, state, requested_capabilities,
        )
        if cap_query and cap_query != queries[0]:
            queries.append(cap_query)

    aggregated: list[dict] = []
    credits = 0
    search_depth_param = "advanced" if depth in (DEPTH_ADVANCED, DEPTH_DEMO) else "basic"
    try:
        for q in queries:
            resp = client.search(
                query=q,
                search_depth=search_depth_param,
                max_results=5,
            )
            credits += 2 if search_depth_param == "advanced" else 1
            results_list = ((resp or {}).get("results") or []) if isinstance(resp, dict) else []
            if isinstance(results_list, list):
                aggregated.extend(r for r in results_list if isinstance(r, dict))
    except Exception as exc:  # noqa: BLE001
        return _error_result(
            facility_id=facility_id_resolved,
            facility_name=facility_name,
            reason_code=REASON_API_ERROR,
            error_message=_short_error(exc),
            query_used=queries[0] if queries else "",
            credits=credits,
        )

    result = _score_results(
        facility_id=facility_id_resolved,
        facility_name=facility_name,
        city=city,
        state=state,
        capabilities=requested_capabilities,
        depth=depth,
        results=aggregated,
        queries=queries,
        credits=credits,
    )

    cache.set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Public API: batch verification of top recommendations
# ---------------------------------------------------------------------------

def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from object-or-dict ``obj``."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def verify_top_recommendations(
    recommendations: list,
    max_to_verify: int = 3,
    depth: str = DEPTH_BASIC,
    *,
    city: Optional[str] = None,
    state: Optional[str] = None,
    requested_capabilities: Optional[list[str]] = None,
    settings: Any = None,
    cache: Optional[TavilyCache] = None,
    client_factory: Optional[Callable[[str], Any]] = None,
) -> list[WebVerificationResult]:
    """Run :func:`verify_facility_web_presence` on the top ``max_to_verify``
    recommendations.

    ``recommendations`` may be a list of :class:`AgentRecommendation`
    instances *or* dicts. Each item may carry per-item ``city`` / ``state``
    / ``requested_capabilities`` overrides; otherwise the function-level
    arguments are used.

    Returns
    -------
    list[WebVerificationResult]
        One result per verified recommendation, in input order.
        Recommendations beyond ``max_to_verify`` are not verified and
        produce no results.
    """
    if not recommendations:
        return []
    n = max(0, int(max_to_verify))
    if n == 0:
        return []

    out: list[WebVerificationResult] = []
    for rec in recommendations[:n]:
        facility_id   = _get_attr(rec, "facility_id", "") or ""
        facility_name = _get_attr(rec, "name", "") or facility_id
        rec_city      = _get_attr(rec, "city", None) or city
        rec_state     = _get_attr(rec, "state", None) or state
        rec_caps      = _get_attr(rec, "requested_capabilities", None)
        if rec_caps is None:
            rec_caps = _get_attr(rec, "capabilities_required", None) or requested_capabilities

        result = verify_facility_web_presence(
            facility_name=facility_name,
            city=rec_city,
            state=rec_state,
            requested_capabilities=rec_caps,
            depth=depth,
            facility_id=facility_id,
            settings=settings,
            cache=cache,
            client_factory=client_factory,
        )
        out.append(result)
    return out


# ---------------------------------------------------------------------------
# Backward-compatibility shim
# ---------------------------------------------------------------------------

def verify_facility(facility_name: str, api_key: str = "") -> WebVerificationResult:
    """Backward-compat wrapper for the original Stage-1 stub.

    Older callers passed ``(facility_name, api_key)``. The new code path
    reads its key from settings, so we forward to
    :func:`verify_facility_web_presence` with a synthetic settings object
    that carries the supplied ``api_key`` (or skips gracefully if blank).
    """
    from types import SimpleNamespace
    fake_settings = SimpleNamespace(
        tavily_enabled=bool(api_key),
        tavily_api_key=api_key or "",
    )
    return verify_facility_web_presence(
        facility_name=facility_name,
        depth=DEPTH_BASIC,
        settings=fake_settings,
    )
