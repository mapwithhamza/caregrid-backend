# Real Integration Runbook

> Step-by-step guide for running the CareGrid Vector Agent end-to-end
> against the real 10,000-row export, with Tavily and Databricks
> Vector Search switched on or off.

This is the operator's runbook. It covers nothing about the *agent
internals* — for that see `docs/AGENT_OVERVIEW.md`.

---

## 1. Where the dataset goes

Place the real CareGrid backend export at:

```
data/raw/caregrid_backend_export_full.csv
```

Required columns (must all be present, names exact):

```
facility_id, name, facility_type, city, state,
latitude, longitude,
trust_score, trust_category, recommendation_readiness,
combined_medical_evidence, evidence_summary
```

Extra columns (`pin_code`, `phone`, `specialties`, `procedures`,
`equipment`, `capabilities_raw`, …) are tolerated and used by the
evidence builder when present.

`run_agent_demo.py --validate-only`-equivalent behaviour is built in:
the runner aborts cleanly with exit code 2 if any required column is
missing.

---

## 2. Local-only demo (recommended first run)

Requires no external services, no credentials, no network.

```bash
python run_agent_demo.py
```

What happens:

1. CSV loaded (10k rows expected).
2. Required columns validated — exits 2 if anything is missing.
3. Five default queries are run sequentially:
   - Find trusted ICU hospitals in Bihar
   - Find emergency hospitals in Maharashtra
   - Find dialysis centers in Uttar Pradesh
   - Find oncology care in Gujarat
   - Find maternity hospitals in Tamil Nadu
4. Outputs written to:
   - `data/outputs/demo_agent_results.json`
   - `data/outputs/demo_agent_results.md`

Each query line on the console prints `tavily_verified=0` and
`vector_available=False` — confirming nothing external was touched.

---

## 3. Tavily-enabled demo

Use this once the local-only run is healthy. See
`docs/TAVILY_REAL_SMOKE_TEST.md` for the full credit-safety checklist.

### 3a. Configure `.env`

```env
TAVILY_API_KEY=tvly-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TAVILY_ENABLED=true              # or ENABLE_TAVILY=true
TAVILY_DEFAULT_DEPTH=basic
TAVILY_MAX_WEB_VERIFIED=2        # or TAVILY_MAX_RESULTS=2
```

### 3b. Run a single query

```bash
python run_agent_demo.py \
    --query "Find emergency hospitals in Maharashtra" \
    --enable-tavily \
    --web-depth basic \
    --max-web-verified 2 \
    --max-results 5
```

### 3c. Check results

In the JSON output, locate
`results[0].response.recommendations[*].web_verification`. The
`top_url` should be a real public URL; the `top_snippet` should
contain the facility name or address. See
`docs/TAVILY_REAL_SMOKE_TEST.md` §6.

---

## 4. Databricks Vector Search demo (later — when index is ready)

The vector index is provisioned separately by `notebooks/02_create_vector_index_notes.py`.
The runner only flips it on when the workspace is reachable.

### 4a. Configure `.env`

```env
VECTOR_SEARCH_ENABLED=true                 # or ENABLE_VECTOR_SEARCH=true
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
DATABRICKS_TOKEN=dapiXXXXXXXXXXXXXXXXXXXXXXXX
VECTOR_SEARCH_ENDPOINT=caregrid-vector-endpoint
VECTOR_SEARCH_INDEX=workspace.default.caregrid_vector_index
```

### 4b. Run a single query

```bash
python run_agent_demo.py \
    --query "Find trusted ICU hospitals in Bihar" \
    --enable-vector \
    --max-results 5
```

### 4c. Confirm the vector path was actually used

In the JSON output:

```jsonc
{
  "trace_summary": {
    "vector": {
      "enabled": true,
      "available": true,             // <- true means the workspace responded
      "reason": ""                   // <- empty means no fallback was needed
    }
  },
  "retrieval_summary": {
    "vector_count": <int>,           // <- number of hits Databricks returned
    "vector_available": true
  }
}
```

If `available=false`, inspect `reason` — common values:
`vector_search_disabled`, `missing_databricks_host/token/endpoint/index`,
`databricks_sdk_unavailable`, `query_failed: …`. The pipeline silently
falls back to local-only retrieval in that case.

---

## 5. Output files

| File | What it contains |
| --- | --- |
| `data/outputs/demo_agent_results.json` | One entry per query — full `AgentResponse` with `interpreted_intent`, `retrieval_summary`, ranked `recommendations`, `evidence`, `validation_findings`, `trace_summary`, `safety_note`. |
| `data/outputs/demo_agent_results.md` | Human-readable Markdown report with one section per query: intent, retrieval summary, top recommendations table, evidence snippets, validation findings, warning flags, Tavily verification block, safety note. |
| `data/outputs/audit_log.jsonl` | Per-event JSONL audit log written by `AuditLogger` (one line per pipeline stage). |

You can override the paths:

```bash
python run_agent_demo.py \
    --output-json data/outputs/run_2026_04_27.json \
    --output-md   data/outputs/run_2026_04_27.md
```

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `[ERROR] Dataset not found at: data/raw/caregrid_backend_export_full.csv` | CSV not placed yet. | Drop the export at that exact path. |
| `[ERROR] Required columns missing: ['evidence_summary']` | Older export schema. | Regenerate the export from the backend with the v2 schema. |
| Tavily-enabled run shows all `verification_status: skipped` | `.env` not loaded, or `TAVILY_API_KEY` blank. | `python -c "from config.settings import settings; print(bool(settings.tavily_api_key))"` should print `True`. |
| Vector-enabled run shows `vector_available: false`, `reason: missing_databricks_token` | Token not in `.env` or expired. | Mint a new PAT in the Databricks UI, paste into `.env`. |
| `--enable-tavily` and `--enable-vector` together never call vector | Vector retriever genuinely unavailable — engine fell back. | See §4c. The pipeline never raises here, it just degrades. |
| Top maternity recommendation is a dental hospital | Known parser substring over-extraction (e.g. `"OR"` in `"for"`, `"ER"` in `"centers"`). | Documented in `docs/GOLDEN_QUERY_RESULTS.md`. Pending fix in the intent parser. |
| `pytest` fails after editing settings | The local `.env` may be bleeding values into a defaults test. | The fix is already in `tests/test_settings.py::test_settings_defaults` — it disables `_env_file` and clears alias env vars. |

---

## 7. What the runner deliberately does *not* do

- Call Tavily for every facility.
- Call Tavily during a default run (it is opt-in via `--enable-tavily`).
- Touch Databricks unless `--enable-vector` is passed *and* the env is configured.
- Modify the source CSV.
- Persist any secret to disk outside `.env`.
- Catch the wrong exception class — the engine itself is non-raising;
  the runner only catches `Exception` as a belt-and-braces wrapper for
  unexpected callable replacements (e.g. tests).
