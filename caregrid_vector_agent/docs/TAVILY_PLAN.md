# Tavily External Verification — Plan

CareGrid's Tavily layer is an **optional** external web-search step that
sits *after* the recommendation engine has produced a ranked list. It
asks the public web "do these claims look real?" and attaches a
verification status to each recommendation.

The agent **must** continue to function with this layer disabled. Every
code path in `agent_core/tavily_verifier.py` is wrapped to fail safe —
no exception ever escapes back into the agent pipeline.

---

## 1. When to enable Tavily

Enable Tavily when **at least one** of these is true:

- The agent is being run in production / demo mode (not in a hot inner loop).
- A facility has been promoted into the top recommendations and its
  `trust_category` is `Moderate Trust / Verify Before Use`.
- A capability claim was flagged by the validator with
  `recommendation_impact = "downgrade_to_verify_before_use"`.
- The user query carried `web_verification_requested = True`
  (set by the intent parser when it sees phrases like "verify",
  "check online", "official site").

Do **not** enable Tavily when:

- The dataset is being scored offline / in batch evaluation
  (use `local_retriever` only — fast, deterministic, free).
- A facility was already verified within the last 24 hours
  (handled automatically by the cache; see § 5).
- `TAVILY_ENABLED=false` or `TAVILY_API_KEY` is not set.

---

## 2. Public API

```python
from agent_core.tavily_verifier import (
    verify_facility_web_presence,
    verify_top_recommendations,
)
```

### 2.1 `verify_facility_web_presence(...)`

```python
def verify_facility_web_presence(
    facility_name: str,
    city: str | None = None,
    state: str | None = None,
    requested_capabilities: list[str] | None = None,
    depth: str = "basic",
    *,
    facility_id: str | None = None,
    settings: Any = None,
    cache: TavilyCache | None = None,
    client_factory: Callable[[str], Any] | None = None,
) -> WebVerificationResult
```

- Verifies a single facility.
- Always returns a `WebVerificationResult`; **never raises**.
- Reads `TAVILY_*` from `config.settings.settings` unless an explicit
  `settings` object is passed.
- Looks up the in-memory cache first; on cache hit, returns the cached
  result with `cached=True`.

### 2.2 `verify_top_recommendations(...)`

```python
def verify_top_recommendations(
    recommendations: list,
    max_to_verify: int = 3,
    depth: str = "basic",
    *,
    city: str | None = None,
    state: str | None = None,
    requested_capabilities: list[str] | None = None,
    settings: Any = None,
    cache: TavilyCache | None = None,
    client_factory: Callable[[str], Any] | None = None,
) -> list[WebVerificationResult]
```

- Verifies up to `max_to_verify` recommendations in input order.
- Items beyond `max_to_verify` are not verified and produce no result.
- Each `recommendation` may be an `AgentRecommendation` instance or a
  `dict`. Per-item `city` / `state` / `requested_capabilities` override
  the function-level defaults.

---

## 3. Depth modes

| Depth      | Tavily calls (per facility)                               | Tavily `search_depth` | Use                                                         |
| ---------- | --------------------------------------------------------- | --------------------- | ----------------------------------------------------------- |
| `basic`    | 1: `"{name} {city} {state}"`                              | `basic`               | Default; cheapest sanity check                              |
| `advanced` | 1 if no caps, else 2: facility query + capability query   | `advanced`            | Higher confidence, lets us match capability evidence        |
| `demo`     | Same as `advanced` + best-effort official-URL extraction  | `advanced`            | Demo / UI rendering — picks a non-aggregator URL when found |

Unknown depth strings silently fall back to `basic`.

The "official URL" heuristic in `demo` skips known aggregator domains
(`justdial.com`, `practo.com`, `lybrate.com`, `facebook.com`,
`instagram.com`, etc.) and prefers a host whose name overlaps with a
slug derived from the facility name.

---

## 4. WebVerificationResult fields

The Stage-12 schema (`agent_core/schemas.py`) extends the original
verifier output with the fields below. All are optional with safe
defaults — older callers that read only `verified` / `sources` /
`summary` continue to work.

| Field                  | Type            | Meaning                                                                                  |
| ---------------------- | --------------- | ---------------------------------------------------------------------------------------- |
| `facility_id`          | `str`           | Canonical ID (defaults to `facility_name` if no ID supplied).                            |
| `query_used`           | `str`           | The first Tavily query that was sent (for audit logs).                                   |
| `verified`             | `bool`          | Convenience: `True` iff `verification_status == "verified"`.                             |
| `sources`              | `list[str]`     | Up to 5 deduped URLs from the result set.                                                |
| `summary`              | `str`           | `top.content[:500]` — short text summary of the strongest hit.                           |
| `cached`               | `bool`          | `True` if served from the in-memory cache.                                               |
| **`web_checked`**      | `bool`          | `True` iff a Tavily call was actually attempted.                                         |
| **`web_available`**    | `bool`          | `True` iff Tavily replied with anything (even an empty result list).                     |
| **`matched_name`**     | `str`           | The facility name when it appeared in any title/content; else `""`.                      |
| **`matched_location`** | `str`           | `"city, state"` of whichever location strings were found in any result; else `""`.       |
| **`matched_capability`** | `list[str]`   | Sorted lowercase capability tokens that were found in any result.                        |
| **`top_url`**          | `str`           | URL of the top result (or the official-looking URL in `demo` mode).                      |
| **`top_snippet`**      | `str`           | `top.content[:280]`.                                                                     |
| **`verification_score`** | `float`       | `[0, 1]` — see scoring rubric below.                                                     |
| **`verification_status`** | `str`        | `verified` \| `partial` \| `unverified` \| `skipped` \| `error`.                         |
| **`verification_notes`** | `list[str]`   | Human-readable notes for audit trace.                                                    |
| **`error_message`**    | `str \| None`  | Single-line, ≤200 chars; only set when `verification_status == "error"`.                 |
| **`credits_estimated`** | `int \| None` | Approximate Tavily credits consumed (1 per basic call, 2 per advanced call).             |

---

## 5. Scoring rubric

Each Tavily search aggregates up to 5 results across all queries for
the facility. We then score them additively:

| Signal                                | Weight |
| ------------------------------------- | -----: |
| Facility name appears anywhere        |   0.4  |
| City appears anywhere                 |   0.2  |
| State appears anywhere                |   0.1  |
| At least one requested capability hit |   0.2 × `min(1, hits/requested)` |
| Demo: official-looking URL found      |   0.1  |

Final score is clipped to `[0, 1]`. Status mapping:

| Score range  | Status        | Recommendation impact                      |
| ------------ | ------------- | ------------------------------------------ |
| `>= 0.7`     | `verified`    | Promote / keep (no downgrade).             |
| `[0.4, 0.7)` | `partial`     | Show "Verify with facility" badge.         |
| `< 0.4`      | `unverified`  | Add explicit warning to recommendation.    |
| —            | `skipped`     | Tavily disabled / API key missing.         |
| —            | `error`       | Surface as warning; do not crash.          |

---

## 6. Cache

The verifier uses an in-memory **TTL cache** (default 24 hours)
implemented in `agent_core/tavily_cache.py`. The cache key is
deterministic and built from:

```
name=<lower(facility_name)> | city=<lower(city)> | state=<lower(state)>
| caps=<sorted, deduped, lower-cased capabilities>
| depth=<lower(depth)>
```

This means:

- The same facility queried twice within 24h costs **one** Tavily call.
- Capability lists `["ICU", "dialysis"]` and `["dialysis", "ICU"]` hit
  the same cache entry.
- Different `depth` values cache **separately** — switching from
  `basic` to `advanced` for the same facility is *not* a cache hit.
- **Errors are not cached** — a transient failure does not poison
  subsequent retries.
- TTL defaults to `DEFAULT_TTL_SECONDS = 24 * 60 * 60`, configurable
  per `TavilyCache(ttl_seconds=...)`.

A module-level singleton is exposed via `get_default_cache()`. Tests
reset state by passing a fresh `TavilyCache(ttl_seconds=3600)` to each
call.

The legacy file-based `load_cache(facility_id)` / `save_cache(...)`
helpers are preserved in the same module so any older script keeps
working, but new code should use `TavilyCache`.

---

## 7. Environment variables

Configured in `config/settings.py` (read from `.env`):

| Variable                  | Default     | Meaning                                                                  |
| ------------------------- | ----------- | ------------------------------------------------------------------------ |
| `TAVILY_ENABLED`          | `false`     | Master switch. If `false`, the verifier always returns `skipped`.        |
| `TAVILY_API_KEY`          | _(empty)_   | Tavily API key. If blank, the verifier returns `skipped` even if enabled.|
| `TAVILY_DEFAULT_DEPTH`    | `basic`     | Default depth used when callers don't specify one.                       |
| `TAVILY_MAX_WEB_VERIFIED` | `3`         | Default upper bound for `verify_top_recommendations.max_to_verify`.      |
| `TAVILY_CACHE_DIR`        | `data/tavily_cache` | Used by the legacy file cache only.                              |

**No secret is ever written to logs, audit traces, or test fixtures.**
The verifier reads `TAVILY_API_KEY` from settings and forwards it once
to the Tavily client constructor.

---

## 8. Failure modes (graceful degradation)

| Trigger                                              | Status     | What is logged                                  |
| ---------------------------------------------------- | ---------- | ----------------------------------------------- |
| `TAVILY_ENABLED=false`                               | `skipped`  | `tavily_disabled`                               |
| `TAVILY_API_KEY` empty                               | `skipped`  | `missing_tavily_api_key`                        |
| `tavily-python` package not installed                | `error`    | `tavily_sdk_unavailable` + short import error   |
| `TavilyClient(...)` raises a non-import exception    | `error`    | `tavily_api_error` + `<ExceptionType>: <msg>`   |
| `client.search(...)` raises any exception            | `error`    | `tavily_api_error` + `<ExceptionType>: <msg>`   |
| Tavily returns malformed payload (`"not a dict"`, …) | `unverified` | `No matching results returned by Tavily.`     |

`error_message` is normalised to a single line, capped at 200 chars,
so audit logs never have to carry multi-line stack traces.

---

## 9. Integration sketch

The recommendation engine (Stage 13, not yet implemented) will compose
the layers like this:

```python
# 1. Local fallback / vector retriever produces a ranked candidate list.
candidates = retrieve_local_candidates(df, intent)
# OR vector_retriever.search(query=..., filters=..., num_results=20)

# 2. Validator emits findings per (record, capability).
all_findings = []
for c in candidates:
    snippets = extract_evidence_snippets(c.raw_record, intent.capabilities_required)
    all_findings.extend(
        validate_candidate(c.raw_record, intent.capabilities_required, snippets)
    )

# 3. Recommendation engine ranks survivors and produces top-K AgentRecommendations.
top_recs = recommend(candidates, all_findings, intent)

# 4. Optional Tavily verification on the very top.
if intent.web_verification_requested:
    web = verify_top_recommendations(
        top_recs,
        max_to_verify=settings.tavily_max_web_verified,
        depth=settings.tavily_default_depth,
        city=intent.city,
        state=intent.state,
        requested_capabilities=intent.capabilities_required,
    )
    # Attach to recommendations by facility_id.
    by_id = {r.facility_id: r for r in web}
    for rec in top_recs:
        rec.web_verification = by_id.get(rec.facility_id)
```

---

## 10. Cost & rate-limiting notes

- A `basic` search costs **1 credit**; an `advanced` search costs **2 credits**.
- `verify_top_recommendations` defaults to `max_to_verify=3`, so the
  worst case for a single user query is:
  - `basic`:    `3 × 1 = 3 credits`
  - `advanced`: `3 × 2 advanced calls × 2 credits = 12 credits`
  - `demo`:     same as `advanced`.
- The 24h cache makes repeated queries against the same facility free.
- Always increment `credits_estimated` so the audit log can sum spend
  across a session.

---

## 11. Test contract

`tests/test_tavily_verifier.py` covers:

- Disabled / missing-key paths return `skipped` and never invoke the
  client factory.
- Mocked successful responses map cleanly to `verified` /
  `partial` / `unverified` based on score.
- Cache prevents duplicate calls for the same facility.
- Cache key correctly differentiates depth and capabilities, but
  ignores capability ordering.
- TTL expiry forces a fresh call after the configured window.
- `verify_top_recommendations` respects `max_to_verify` and `depth`,
  works with both `AgentRecommendation`-like objects and dicts, and
  returns an empty list for empty / zero-limit input.
- Error paths (`ImportError` → `tavily_sdk_unavailable`, other client
  construction errors → `tavily_api_error`, `client.search` raises →
  `tavily_api_error`) all return `error` status with a short
  single-line message.
- Errors are **not** cached.
- `WebVerificationResult` defaults are safe (no required fields beyond
  `facility_id`).

The Tavily SDK itself is **never** imported during tests — every test
injects a `MagicMock` factory.
