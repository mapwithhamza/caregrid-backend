# Tavily Real Smoke Test — Runbook

> **Purpose:** confirm the end-to-end agent pipeline can issue *real*
> Tavily searches against the public web for the top recommendations
> of a single query, without leaking credits and without breaking
> any other component.

This document is a runbook, not a tutorial. It assumes the rest of the
agent (intent parser, local retriever, recommendation engine) is
already working — the goal here is to flip the Tavily switch on,
verify exactly one query, and confirm the result is **real and not
mocked**.

---

## 1. Prerequisites

- The real 10k-row export at
  `data/raw/caregrid_backend_export_full.csv`.
- A Tavily account and an API key starting with `tvly-`. Get one at
  <https://app.tavily.com>.
- `tavily-python` installed (already in `requirements.txt`).

---

## 2. Configure `.env`

Create `.env` in the project root (gitignored). Either env-var name in
each pair works — `config/settings.py` reads both:

```env
# Tavily (real)
TAVILY_API_KEY=tvly-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TAVILY_ENABLED=true            # or ENABLE_TAVILY=true
TAVILY_DEFAULT_DEPTH=basic
TAVILY_MAX_WEB_VERIFIED=2      # or TAVILY_MAX_RESULTS=2

# Vector search stays OFF for this smoke test
VECTOR_SEARCH_ENABLED=false    # or ENABLE_VECTOR_SEARCH=false
```

> **Never commit `.env`.** It is listed in `.gitignore`. Rotate any key
> that has been exposed (chat history, screenshot, terminal recording).

---

## 3. Local-only sanity check (no Tavily)

Run the default demo first to confirm the pipeline is healthy
*without* spending Tavily credits:

```bash
python run_agent_demo.py
```

Expected:

- 5 default queries run.
- Console shows `enable_tavily : False`.
- Each line ends with `tavily_verified=0  vector_available=False`.
- `data/outputs/demo_agent_results.json` and
  `data/outputs/demo_agent_results.md` are written.

If this step fails, **stop** — fix the local pipeline before paying for
Tavily calls.

---

## 4. Tavily-enabled smoke command

A single targeted query, basic depth, capped at 2 verifications:

```bash
python run_agent_demo.py \
    --query "Find emergency hospitals in Maharashtra" \
    --enable-tavily \
    --web-depth basic \
    --max-web-verified 2 \
    --max-results 5
```

Expected console output highlights:

- `enable_tavily      : True`
- `TAVILY_API_KEY     : present (real call expected)`
- One line of the form
  `returned=5  local=…  merged=…  tavily_verified=2  vector_available=False`.

---

## 5. Expected result fields

For every recommendation the runner verified, the JSON output contains
a populated `web_verification` block with these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `web_checked` | bool | Tavily was actually called for this facility. |
| `web_available` | bool | Tavily returned a payload at all. |
| `verification_status` | str | `verified` / `partial` / `unverified` / `skipped` / `error`. |
| `verification_score` | float | 0.0 – 1.0 — name + location + capability match. |
| `top_url` | str | The most "official-looking" URL Tavily returned. |
| `top_snippet` | str | One-paragraph excerpt from that URL. |
| `matched_name` / `matched_location` / `matched_capability` | str / str / list[str] | Which fields the public web confirmed. |
| `credits_estimated` | int | 1 for `basic`, ~4 for `advanced` per facility. |
| `error_message` | str or null | Populated only on `status="error"`. |

The same data is rendered in the Markdown report under `## Tavily
Verification` for each query.

---

## 6. Confirming Tavily was real, not mocked

Sanity checks (any one of these is conclusive):

1. **`top_url` is reachable.** Open it in a browser. If it loads a real
   public web page, the call hit the real Tavily API.
2. **`top_snippet` contains text** that mentions the facility name or
   address. Mocked tests use deterministic placeholder text such as
   `"mocked snippet for testing"` — the live API never produces that.
3. **`credits_estimated` is non-zero.** The runner reports the running
   total in the console; a fresh run with a basic query and
   `--max-web-verified 2` should report
   `credits_estimated`: ~2 in the per-query line and exactly the same
   total in `trace_summary["tavily"]["credits_estimated"]`.
4. **Tavily dashboard.** Check
   <https://app.tavily.com/usage> immediately before and after the
   command — the credit counter must move.

If `web_checked=True` but `top_url=""` and `top_snippet=""`, the call
was real but returned no usable hits — that is a `unverified` /
`partial` status, not an error.

---

## 7. Credit safety rules

These rules exist so an accidental loop or a runaway script cannot
drain a Tavily account.

- **Never** call Tavily for *all* facilities in the dataset. The
  pipeline is designed to verify only the top `max_web_verified`
  recommendations per query (default 2, hard-capped per call).
- **Never** raise `TAVILY_DEFAULT_DEPTH` to `advanced` for full
  default-query batches without a reason. `advanced` runs ~4 credits
  per facility instead of ~1.
- **Never** loop the runner from inside a script without an explicit
  rate limit; Tavily caches identical calls for 24 h via
  `TavilyCache`, but a loop with shifting parameters will defeat that.
- **Cap the smoke test.** A `--max-web-verified 2` smoke run with
  `--web-depth basic` against one query costs ≤ 2 credits — one for
  the local retriever's two top facilities. Anything more is a sign
  something else is wrong.
- **Rotate the key on first sign of leakage.** Generate a new key on
  the dashboard and replace the value in `.env`.

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `TAVILY_API_KEY     : MISSING` in the console banner | `.env` not loaded, or variable mistyped. | Confirm `.env` exists, then `python -c "from config.settings import settings; print(bool(settings.tavily_api_key))"`. |
| All `web_verification` show `verification_status: skipped` | `tavily_enabled=False` in settings, or `--enable-tavily` not passed. | Pass `--enable-tavily`, or set `TAVILY_ENABLED=true` / `ENABLE_TAVILY=true`. |
| All `web_verification` show `verification_status: error` | API outage, expired key, or rate-limit. | Inspect `error_message` in the JSON. Wait a minute and retry. |
| Status is `unverified` for a well-known hospital | Real but no high-confidence match — Tavily ranked aggregator pages first. | Switch to `--web-depth demo` for one facility to surface an "official-looking" URL. |
| Console shows non-zero `tavily_verified` but zero `credits_estimated` | All hits served from cache. | This is the expected speedup; clear the cache or change the query to force a fresh call. |
