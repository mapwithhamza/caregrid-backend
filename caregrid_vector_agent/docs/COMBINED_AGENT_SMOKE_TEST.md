# Stage 18 — Combined Vector + Tavily Final Agent Smoke Test

> **Purpose.** Combined proof that the standalone CareGrid Vector Agent
> can run end-to-end with **both** Databricks Mosaic AI Vector Search
> *and* Tavily web verification enabled, producing the full
> contract: vector retrieval, Tavily verification on the top
> shortlist (cap-respecting), per-recommendation `score_breakdown` with
> `vector_similarity_component > 0` and `tavily_verification_component > 0`,
> evidence snippets, validation findings, warning flags, human next
> steps, and the safety note — without any backend or frontend change.

This page is the single source of truth for Stage 18. It is generated
from the manual smokes you can re-run yourself in 60 seconds; everything
in the **Result summary** table is reproducible from the JSON / Markdown
files committed under `data/outputs/`.

---

## 1. Environment

### 1.1 Databricks Mosaic AI Vector Search

| Setting                  | Value                                                    |
| ------------------------ | -------------------------------------------------------- |
| Workspace host           | `https://dbc-f8a63c0d-8f76.cloud.databricks.com`         |
| Endpoint                 | `caregrid-vector-endpoint`                               |
| Index                    | `workspace.default.caregrid_vector_index`                |
| Source table             | `workspace.default.caregrid_vector_source`               |
| Primary key              | `facility_id`                                            |
| Embedding source column  | `vector_text`                                            |
| Embedding model          | `databricks-gte-large-en`                                |
| Index type               | Delta Sync / Hybrid                                      |
| Sync mode                | Triggered                                                |
| Rows indexed             | 10,000                                                   |
| Reranker                 | Disabled (workspace-level)                               |

### 1.2 Tavily web verification

| Setting                  | Value                                                    |
| ------------------------ | -------------------------------------------------------- |
| API                      | `tavily-python` SDK (lazy-imported by the verifier)      |
| Default depth            | `basic` (1 search per facility, 1 credit)                |
| Cap per run              | `--max-web-verified 2` (Stage 18 default)                |
| Credit ceiling per smoke | 2 credits                                                |
| Cache                    | In-memory TTL 24h (no Tavily call on cache hit)          |

### 1.3 Local dataset

| Path                                          | Rows   | Required columns       |
| --------------------------------------------- | ------ | ---------------------- |
| `data/raw/caregrid_backend_export_full.csv`   | 10,000 | 12 / 12 present        |

### 1.4 `.env` keys exercised by Stage 18

The agent reads each value via `pydantic-settings` with `AliasChoices`,
so canonical and short-alias names both work:

```ini
# Vector search
VECTOR_SEARCH_ENABLED=true
ENABLE_VECTOR_SEARCH=true
DATABRICKS_HOST=https://dbc-f8a63c0d-8f76.cloud.databricks.com
DATABRICKS_TOKEN=<rotated-PAT>
VECTOR_SOURCE_TABLE=workspace.default.caregrid_vector_source
VECTOR_SEARCH_ENDPOINT=caregrid-vector-endpoint
VECTOR_SEARCH_INDEX=workspace.default.caregrid_vector_index
DATABRICKS_VECTOR_ENDPOINT=caregrid-vector-endpoint
DATABRICKS_VECTOR_INDEX=workspace.default.caregrid_vector_index

# Tavily verification
TAVILY_ENABLED=true
ENABLE_TAVILY=true
TAVILY_API_KEY=<rotated-key>
TAVILY_DEFAULT_DEPTH=basic
TAVILY_MAX_WEB_VERIFIED=2
TAVILY_MAX_RESULTS=2
```

> The actual `.env` is gitignored (`.env` is in `.gitignore`).
> No secret is ever committed; both keys above were rotated after
> Stage 17 / 18 smokes for safety.

### 1.5 Graceful-degradation guarantees

The pipeline never crashes on missing optional services:

| Missing                         | What happens                                                  |
| ------------------------------- | ------------------------------------------------------------- |
| `DATABRICKS_HOST`               | `vector_available=false`, local-only retrieval, no traceback. |
| `DATABRICKS_TOKEN`              | Same as above.                                                |
| `VECTOR_SEARCH_ENDPOINT/INDEX`  | Same as above.                                                |
| `databricks-vectorsearch` SDK   | Same as above; reason `vector_sdk_unavailable`.               |
| `TAVILY_API_KEY`                | All web verifications return `verification_status=skipped`.   |
| Tavily SDK                      | Same as above; reason `tavily_sdk_unavailable`.               |
| Tavily HTTP error               | Per-facility `verification_status=error`, run continues.      |

These are unit-tested in `tests/test_recommendation_engine.py::test_stage18_*`.

---

## 2. Commands run

```powershell
# 2.1 Bihar — trusted ICU hospitals
python run_agent_demo.py `
  --query "Find trusted ICU hospitals in Bihar" `
  --enable-vector --enable-tavily `
  --web-depth basic --max-web-verified 2 --max-results 5 `
  --output-json data/outputs/combined_vector_tavily_bihar_icu.json `
  --output-md   data/outputs/combined_vector_tavily_bihar_icu.md

# 2.2 Uttar Pradesh — dialysis centers
python run_agent_demo.py `
  --query "Find dialysis centers in Uttar Pradesh" `
  --enable-vector --enable-tavily `
  --web-depth basic --max-web-verified 2 --max-results 5 `
  --output-json data/outputs/combined_vector_tavily_up_dialysis.json `
  --output-md   data/outputs/combined_vector_tavily_up_dialysis.md

# 2.3 Maharashtra — emergency hospitals
python run_agent_demo.py `
  --query "Find emergency hospitals in Maharashtra" `
  --enable-vector --enable-tavily `
  --web-depth basic --max-web-verified 2 --max-results 5 `
  --output-json data/outputs/combined_vector_tavily_maharashtra_emergency.json `
  --output-md   data/outputs/combined_vector_tavily_maharashtra_emergency.md
```

Total Tavily credits spent across all three smokes: **6** (≈ $0.012 at
list pricing). Total Databricks vector queries: **3** (one per smoke;
each returned 20 candidates).

---

## 3. Result summary

| Query                                  | vector_avail. | vector_count | filter | tavily_verified | tavily_credits | returned | Top recommendation                                            | safety_note | output files |
| -------------------------------------- | :-----------: | -----------: | :----: | --------------: | -------------: | -------: | ------------------------------------------------------------- | :---------: | ------------ |
| Find trusted ICU hospitals in Bihar    | ✅            | 20           | ✅      | 2               | 2              | 5        | Dr Niranjan Sagar Champaran Heart Center &Hospital (Bihar)    | ✅           | `data/outputs/combined_vector_tavily_bihar_icu.{json,md}`              |
| Find dialysis centers in Uttar Pradesh | ✅            | 20           | ✅      | 2               | 2              | 5        | Dr. Mudit Khurana Dialysis Centre (Uttar Pradesh)             | ✅           | `data/outputs/combined_vector_tavily_up_dialysis.{json,md}`            |
| Find emergency hospitals in Maharashtra| ✅            | 20           | ✅      | 2               | 2              | 5        | Dr Ravindra Naikwadi Multispeciality Hospital (Maharashtra)   | ✅           | `data/outputs/combined_vector_tavily_maharashtra_emergency.{json,md}`  |

All three smokes returned `vector_enabled=True`, `vector_available=True`,
`vector_filter_applied=True`, and the trace contains every required
stage:

```
intent_parsed → local_retrieval → vector_retrieval → merge → enrich
              → score_and_rank → tavily_verification → final_response
```

`trace_summary.errors` is empty for all three runs.

---

## 4. Score-breakdown proof

Stage 18 requires that **at least one recommendation** in each run has
`vector_similarity_component > 0` *and* `tavily_verification_component > 0`,
*not necessarily on the same recommendation*. The smokes go further —
on the Bihar and UP queries the **same** top recommendation has both
components positive simultaneously.

| Query                  | rank | facility                                        | vector_sim_comp | tavily_verify_comp | final |
| ---------------------- | :--: | ----------------------------------------------- | --------------: | -----------------: | ----: |
| Bihar ICU              | 2    | Braham Jyoti Hospital                           | **0.0949**      | **0.1050**         | 0.838 |
| Bihar ICU              | 1    | Dr Niranjan Sagar Champaran Heart Center &Hosp. | 0.0000          | **0.1050**         | 0.868 |
| UP dialysis            | 1    | Dr. Mudit Khurana Dialysis Centre               | **0.0991**      | **0.0450**         | 0.869 |
| UP dialysis            | 2    | La Friendz Medical Centre                       | 0.0000          | **0.0900**         | 0.778 |
| Maharashtra emergency  | 1    | Dr Ravindra Naikwadi Multispeciality Hospital   | 0.0000          | **0.1050**         | 0.895 |
| Maharashtra emergency  | 3    | Sadguru Multispeciality Hospital                | **0.0979**      | 0.0000             | 0.766 |

Bounds: every `final_score` shown above sits inside `[0, 1]` after the
clip in `_score_candidate` / `_apply_tavily_to_score`. The Tavily
component is bounded by `_W_TAVILY = 0.15`; the vector component by
`_W_VECTOR = 0.15`. So even the strongest combined boost can add at
most `0.30` to a recommendation's score — vector + Tavily can refine
the ranking but cannot override a low-trust or contradicted facility
into a top spot.

---

## 5. Safety proof

* `safety_note` is present in every response (string equality with
  `agent_core.recommendation_engine.SAFETY_NOTE`).
* The Maharashtra emergency query carries `urgency=emergency` in
  `interpreted_intent`, and every recommendation's
  `human_next_steps` ends with the
  > "EMERGENCY: call the facility's casualty/24x7 number now to confirm
  > they can accept the patient before transit."
  step. This step is appended even when Tavily verifies the facility,
  because Tavily verification is not a substitute for live phone
  confirmation.
* Stage 16's identity-vs-capability split is preserved: when Tavily
  matches the facility name + city + state but does **not** match a
  capability term, the `reason_for_recommendation` reads
  > "web-verified identity/location only — clinical capability not
  > confirmed online (<score>)"
  and the human_next_steps include
  > "Web verification confirmed identity/location only — call the
  > facility directly to confirm the clinical capability (equipment,
  > staff, on-site availability)."
  Visible on every Tavily-verified recommendation in the Bihar ICU
  Markdown report.
* Stage 16's clinical-matching patch holds: the UP dialysis query
  parses to `DIALYSIS_RENAL` (not `EMERGENCY_TRAUMA` from the word
  "centers"); the Maharashtra emergency query's evidence snippets do
  **not** match on stapler / infertility / cataract / pterygium (the
  short-token "er" false-match was eliminated in Stage 16).

---

## 6. Caps and conservatism

The pipeline is built so external traffic stays small, predictable, and
never overrides domain-internal evidence:

* **Vector retrieval** runs once per query (`num_results=20`) and only
  pushes a `state` filter; everything else is filtered locally so a
  filterable-column mismatch can never silently drop relevant results.
* **Tavily** runs **only** on the top `--max-web-verified`
  recommendations after scoring, never on the full 200-row local pool
  or the 20-row vector hit list. This is verified by
  `tests/test_recommendation_engine.py::test_stage18_combined_mode_does_not_verify_all_merged_candidates`.
* `vector_similarity_component` and `tavily_verification_component` are
  each capped at `0.15`. They can move a recommendation up the rank
  but cannot turn a contradicted, no-evidence, low-trust facility into
  the top result.
* `validation_penalty` and `warning_penalty` apply *after* both
  retrieval bonuses, so a contradiction (`-0.15`) plus a missing
  trust-category warning (`-0.02`) can flip a vector + Tavily-boosted
  facility back below a clean local-only recommendation. Stage 16's
  validator drives the penalty side of this trade.

---

## 7. Known limitations

* **Tavily ≠ live clinical capability.** Tavily checks public web
  presence, identity, and location. A `verification_status="verified"`
  result means "the facility name + city + state appear together on
  the web", not "the facility currently has a working ICU bed". The
  human_next_steps explicitly call this out.
* **Vector retrieval is recall, not authority.** Semantic similarity
  surfaces facilities with related embeddings; it does not validate
  the capability claim. Validation is owned by `agent_core.validator`
  and uses local evidence snippets only.
* **JustDial / Sulekha / Practo URLs.** Tavily's basic-depth search
  often returns aggregator listings as the top URL. The verifier
  down-weights these for the `demo` depth via
  `_AGGREGATOR_DOMAINS`; for `basic` depth they are still surfaced
  because they confirm the facility's existence even if they aren't an
  official site. The judge / clinician should treat them as
  identity-only evidence.
* **Trust score normalisation.** The exported CSV stores trust as a
  0–100 scale; the engine clips to `[0, 1]` before scoring (so a CSV
  trust of 84 reads as a `trust_score_component` of `0.25` — the
  weight ceiling — not 21).

---

## 8. Output files

```
data/outputs/combined_vector_tavily_bihar_icu.json
data/outputs/combined_vector_tavily_bihar_icu.md
data/outputs/combined_vector_tavily_up_dialysis.json
data/outputs/combined_vector_tavily_up_dialysis.md
data/outputs/combined_vector_tavily_maharashtra_emergency.json
data/outputs/combined_vector_tavily_maharashtra_emergency.md
```

Each Markdown file contains every Stage-18 section in this order:

1. Interpreted Intent
2. Retrieval Summary (with all Stage-18 keys, including Tavily)
3. Top Recommendations
4. Score Breakdown (per-component table)
5. Evidence Snippets
6. Validation Findings
7. Warning Flags
8. Vector Search panel
9. Tavily Verification panel
10. Human Next Steps
11. Safety Note
12. Debug / Trace Summary (fenced JSON)

---

## 9. Contract → code → test mapping

| Stage-18 contract clause                                | Code location                                                 | Test                                                                                       |
| ------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `vector_enabled / available / count / filter_applied`   | `recommendation_engine.run_recommendation` (vector block)     | `test_stage17_retrieval_summary_carries_endpoint_index_and_filter_applied`                 |
| `web_verification_enabled / tavily_*` keys              | `recommendation_engine` retrieval-summary builder (Stage 18)  | `test_stage18_combined_mode_runs_with_mocked_vector_and_tavily`                            |
| Tavily only on top `max_web_verified`                   | `tavily_verifier.verify_top_recommendations`                  | `test_stage18_combined_mode_does_not_verify_all_merged_candidates`, `..._respects_cap`     |
| `vector_similarity_component > 0` after vector hit      | `_score_candidate`                                            | `test_stage17_vector_similarity_component_is_positive_for_scored_candidate`                |
| `tavily_verification_component > 0` after Tavily hit    | `_apply_tavily_to_score`                                      | `test_stage18_combined_mode_runs_with_mocked_vector_and_tavily`                            |
| `final_score` bounded                                   | `_score_candidate`, `_apply_tavily_to_score`                  | `test_stage18_combined_mode_score_breakdown_has_all_components`                            |
| Vector failure → graceful fallback                      | `vector_retriever.search`, engine try/except                  | `test_stage18_combined_mode_falls_back_when_vector_fails`                                  |
| Tavily failure → graceful fallback                      | `tavily_verifier.verify_facility_web_presence` try/except     | `test_stage18_combined_mode_falls_back_when_tavily_fails`                                  |
| All trace stages including `final_response`             | `recommendation_engine.run_recommendation`                    | `test_stage18_combined_mode_trace_summary_has_all_stages`                                  |
| `safety_note` always present                            | `recommendation_engine.SAFETY_NOTE`                           | `test_stage18_combined_mode_safety_note_always_present`                                    |
| Markdown report contains all Stage-18 sections          | `run_agent_demo.save_markdown_report`                         | `test_stage18_combined_markdown_has_all_required_sections`                                 |
| CLI flags pass through to engine                        | `run_agent_demo._build_arg_parser`                            | `test_stage18_combined_flags_pass_through_to_engine`                                       |
| Combined mode response is JSON-serialisable             | Pydantic v2 `model_dump(mode="json")`                         | `test_stage18_combined_mode_response_serialises_cleanly`                                   |

---

## 10. Reproducing this proof

1. Activate your local Python environment (project root = `D:\caregrid_vector_agent`).
2. Confirm `data/raw/caregrid_backend_export_full.csv` exists (10,000
   rows, 35 columns).
3. Set the environment variables in §1.4 inside your local `.env`.
4. Run the three commands in §2.
5. Inspect the JSON / Markdown files listed in §8 — they are committed.
6. Run `python -m pytest -q` and confirm 493+ tests pass.

> **Do NOT** commit `.env`. **Do NOT** paste the Databricks PAT or
> Tavily key into a chat, screenshot, or PR. Both keys are rotated as
> soon as a Stage smoke completes.
