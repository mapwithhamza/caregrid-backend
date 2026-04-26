# CareGrid Vector Agent — Progress Log

> **Rule:** Update this file after every prompt or significant change.

---

## Current Stage

**Stage 18 — Combined Vector + Tavily Final Agent Smoke Test.
First end-to-end proof that the standalone agent runs the **full
contract** with both retrieval arms live: local CSV + Databricks
Mosaic AI Vector Search + Tavily web verification, all gracefully
falling back when any one arm is missing or fails. The orchestration
contract was tightened in `agent_core/recommendation_engine.py`:
Tavily now runs **only** on the post-ranking top shortlist (capped by
`max_web_verified`), never on the 10,000-row vector haystack or the
20-row vector hit list, and the final-response stage marker is
appended to `trace_stages` *before* `trace_summary` is constructed so
every Stage-18 stage (`intent_parsed → local_retrieval →
vector_retrieval → merge → enrich → score_and_rank →
tavily_verification → final_response`) is visible to downstream
auditors. `retrieval_summary` was extended with the four Stage-18
Tavily keys (`web_verification_enabled`, `tavily_verified_count`,
`tavily_depth`, `tavily_credits_estimated`) so a single dict tells the
operator what each retrieval arm produced; the same numbers live in
`trace_summary["tavily"]` for backward compatibility.
`run_agent_demo.py` gained three new Markdown formatters
(`_format_score_breakdown_section`, `_format_human_next_steps_section`,
`_format_trace_summary_section`) and the demo report now contains all
13 Stage-18 panels in order — query, interpreted intent, retrieval
summary, vector panel, Tavily panel, top recommendations, score
breakdown, evidence snippets, validation findings, warning flags,
human next steps, safety note, and a fenced trace_summary block —
making every JSON / Markdown pair a self-contained judge / clinician
artefact. The console output for `run_demo_queries` was upgraded to
print `tavily_enabled`, `tavily_verified_count`, `tavily_credits`,
`vector_available`, `vector_count`, `vector_filter_applied` on a single
line. `.env` was flipped to `TAVILY_ENABLED=true` /
`ENABLE_TAVILY=true`; `.env.example` already documented the canonical
+ alias names so no schema changes were needed in
`config/settings.py`. A subtle Tavily cache-pollution bug surfaced in
the new combined tests — earlier suites left a `0.0` verification
score cached in the module-level `TavilyCache`, which short-circuited
later mocks and silently zeroed `tavily_verification_component` even
though `tavily_verified_count > 0`. The fix is a pytest `autouse`
fixture (`reset_tavily_default_cache` in
`tests/test_recommendation_engine.py`) that calls
`tavily_cache.reset_default_cache()` before and after every Stage-18
test, restoring full test isolation. **Test count: 493 / 493 passing
(no real network calls during pytest).** Twelve new Stage-18
combined-mode tests cover end-to-end mocked vector + Tavily flow,
all-nine score-breakdown components, the `max_web_verified` cap,
graceful degradation when either arm fails, the full trace stage list,
safety-note presence, JSON serialisability, and CLI flag pass-through.
**Three real combined smokes succeeded** against the live Databricks
index + live Tavily API:

| Query                                  | vector_count | tavily_verified | returned | Top recommendation                                          |
|----------------------------------------|-------------:|----------------:|---------:|-------------------------------------------------------------|
| Find trusted ICU hospitals in Bihar    | 20           | 2               | 5        | Dr Niranjan Sagar Champaran Heart Center &Hospital (Bihar)  |
| Find dialysis centers in Uttar Pradesh | 20           | 2               | 5        | Dr. Mudit Khurana Dialysis Centre (Uttar Pradesh)           |
| Find emergency hospitals in Maharashtra| 20           | 2               | 5        | Dr Ravindra Naikwadi Multispeciality Hospital (Maharashtra) |

For each smoke `vector_enabled=true`, `vector_available=true`,
`vector_filter_applied=true`, `web_verification_enabled=true`,
`tavily_credits_estimated=2`, `safety_note` present, and at least one
recommendation has both `vector_similarity_component > 0` *and*
`tavily_verification_component > 0` (Bihar: Braham Jyoti Hospital
0.0949 / 0.1050 / final 0.838; UP: Dr. Mudit Khurana 0.0991 / 0.0450 /
final 0.869; Maharashtra: vector + Tavily on different recs but both
positive in the top-5 — Sadguru 0.0979 / 0.0000 and Dr Ravindra
Naikwadi 0.0000 / 0.1050 / final 0.895). The Stage-16 clinical-match
patch held — UP intent stayed `DIALYSIS_RENAL` (no false
`EMERGENCY_TRAUMA` from "centers"); Maharashtra emergency evidence
contained no false `er`-in-stapler / infertility / cataract /
pterygium matches. No fallback was used; both retrieval arms ran
green. **Files changed (Stage 18):**
`agent_core/recommendation_engine.py`,
`run_agent_demo.py`, `.env`,
`tests/test_recommendation_engine.py`,
`tests/test_run_agent_demo.py`,
`docs/COMBINED_AGENT_SMOKE_TEST.md` (new),
`docs/PROGRESS.md` (this entry),
`docs/DELIVERABLES_STATUS.md`. Six new output proof files in
`data/outputs/combined_vector_tavily_*.{json,md}`. **Next step: Stage
19 — Integrate Standalone Agent into Main Backend API** (read-only
adapter, no main-backend logic changes, the standalone agent stays
the source of truth for retrieval / scoring / verification).**

**Stage 17 — Real Vector-Enabled Agent Smoke Test.
First end-to-end run of the standalone agent against the **live**
Databricks Mosaic AI Vector Search index. The retriever was switched
from `databricks-sdk` → `databricks-vectorsearch` (the package the
main team validated against the real workspace), so the call shape
is now `index.similarity_search(query_text=..., columns=[...],
num_results=..., filters={"state": "Bihar"})` — a native Python dict
filter, never `filters_json`. `agent_core/vector_retriever.py` was
rewritten to (a) drop `latitude` / `longitude` and request only the
eight Stage-17 columns (no `score` — Databricks adds it automatically),
(b) cache the resolved index handle, (c) transparently retry without
filters if the SDK build raises `TypeError` on the `filters=` kwarg
(reporting `filter_applied=false`, `reason="ok_without_filter"`), and
(d) parse both dict-shape (live SDK) and namespace-shape (legacy)
responses. `VectorSearchResponse` gained `filter_applied`, `endpoint`,
and `index` fields so the recommendation engine can echo them back to
the caller. `recommendation_engine.py` now builds a `{"state": ...}`
filter from `intent.state`, populates a richer
`retrieval_summary` (`vector_filter_applied`, `vector_filters_requested`,
`vector_endpoint`, `vector_index`), and surfaces the same data in
`trace_summary["vector"]`. `run_agent_demo.py` prints
`enable_vector` / `vector_available` / `vector_count` /
`vector_filter_applied` to the console, reads `DATABRICKS_HOST`
status from `Settings` (so `.env` values are visible in the banner),
and emits a dedicated `## Vector Search` section in the Markdown
report containing the per-recommendation `vector_similarity_component`.
Settings now accepts the short aliases `DATABRICKS_VECTOR_ENDPOINT` /
`DATABRICKS_VECTOR_INDEX` alongside the existing canonical and long
forms; `requirements.txt` adds `databricks-vectorsearch>=0.40`. Tests
were rewritten to match the new SDK contract (33 vector-retriever
tests covering filter retry, `score`-not-in-columns, dict + legacy
namespace parsing, missing-env paths) and 6 new Stage-17 recommendation
engine + run_agent_demo tests prove the wiring end-to-end with mocks
only — zero real Databricks calls and zero Tavily credits during
automated runs. **Both real smoke queries succeeded against the live
index:** Bihar ICU returned `vector_count=20`, `filter_applied=true`,
top recommendations all in Bihar, with at least one
`vector_similarity_component=0.0949 > 0`; UP dialysis returned
`vector_count=20`, `filter_applied=true`, top result
`Dr. Mudit Khurana Dialysis Centre` with
`vector_similarity_component=0.0991`, intent stayed `DIALYSIS_RENAL`
(Stage 16 patch holds). 481 tests total, all green.**

**Stage 16 — Clinical Matching Quality Patch.
A foundational fix for clinical term matching across the entire agent.
Three new safe-matching helpers in `agent_core/capability_taxonomy.py`
(`normalize_text`, `term_matches`, `find_matching_terms`) enforce
case-insensitive phrase matching with strict word-boundary rules for
short or symbol-bearing tokens (length ≤ 3, or containing
`0–9 / x : &`). This kills the long-standing "ER in centers" /
"OT in support" / "OR in for" false positives at the source. The
`EMERGENCY_TRAUMA` capability was tightened: strong evidence terms are
now restricted to clinically meaningful phrases (`emergency department`,
`trauma centre`, `ambulance`, `24/7`, `ventilator`, `triage`); generic
words like `surgery` and `treatment` no longer satisfy emergency
validation. `DIALYSIS_RENAL` lost the bare keywords `kidney` and `renal`
(which over-matched `kidney stones` and `adrenal`) and now requires
specific phrasings (`nephrology`, `dialysis machine`, `haemodialysis`,
`AV fistula`). `evidence_citation.py`, `validator.py`, `intent_parser.py`,
and `local_retriever.py` were all routed through the new helpers so the
fix propagates uniformly. `local_retriever.py` gained a
`WEIGHT_NAME_MATCH = 3.0` boost so a facility called "Lucknow Dialysis
Centre" outranks a generic clinic that happens to mention `kidney`.
`recommendation_engine.py` adds a 9th score component (`_W_LOCAL_RELEVANCE
= 0.10`, saturating at `local_relevance_score = 15.0`) so depth of local
matches finally influences the final ranking — this is what lets the
trauma centre overtake a generic high-trust hospital on the Maharashtra
emergency query. The engine also clarifies Tavily output: when
`verification_status="verified"` but `matched_capability=[]`, the
`reason_for_recommendation` and `human_next_steps` now explicitly say
**identity/location verified, clinical capability NOT confirmed online —
call the facility to confirm equipment/staff**. A new contradiction rule
`CR_HIGH_ACUITY_CLAIM_NO_EVIDENCE` in `contradiction_rules.py` flags any
facility that claims emergency / trauma / ICU / dialysis / critical care
in `specialties` or `capabilities_raw` but has empty `equipment` AND
empty `procedures` — closing the GQ-010 "sketchy emergency hospital"
loophole. 23 new regression tests in `tests/test_clinical_matching_quality.py`
cover every fixed bug; full suite is 463 tests, all green. Smoke
outputs regenerated under `data/outputs/stage16/` confirm: UP dialysis
no longer trips `EMERGENCY_TRAUMA`, the top dialysis result is an actual
dialysis facility, and the Maharashtra emergency top result is a
genuine trauma/emergency facility.**

**Stage 15 (cont.) — Real Dataset + Real Tavily Smoke Test Runner.
`run_agent_demo.py` runs the full agent pipeline against the real
10,000-row `data/raw/caregrid_backend_export_full.csv` with sensible
safety defaults: Tavily and vector search are both **off** unless
explicitly enabled via `--enable-tavily` / `--enable-vector`. CLI
flags cover query override, max_results, web depth, max-web-verified,
and JSON/Markdown output paths. Outputs include a structured
`AgentResponse` per query (JSON) and a per-query human-readable report
(Markdown). 21 new tests confirm: imports clean, default queries
exact, dataset validator rejects missing columns, JSON/Markdown
writers produce the expected files, and **no real Tavily or
Databricks calls** are made by the test suite (verified via
mock-not-called assertions). Dataset shape confirmed at runtime: 10k
rows × 35 columns, 34 unique states, all 12 required columns
present.**

**Stage 15 — Tavily live wiring & dual env-var name compatibility.
`config/settings.py` now reads three pairs of equivalent env vars via
`pydantic.AliasChoices` so older `.env` files keep working alongside
the canonical names: `TAVILY_ENABLED`/`ENABLE_TAVILY`,
`TAVILY_MAX_WEB_VERIFIED`/`TAVILY_MAX_RESULTS`,
`VECTOR_SEARCH_ENABLED`/`ENABLE_VECTOR_SEARCH`. The Databricks endpoint
and index fields also accept their `DATABRICKS_*`-prefixed variants.
Local `.env` populated with a real Tavily key (gitignored); end-to-end
live smoke against `Apollo Hospitals, Mumbai` returned
`verification_status="verified"` with score 0.7 and a real public URL.
Vector search remains disabled while the Databricks index is being
provisioned separately.**

**Stage 14 — Golden query evaluation suite live: 10 curated queries
in `agent_core/demo_queries.GOLDEN_QUERIES`, full contract +
behavioural test coverage in `tests/test_golden_queries.py`,
human-readable results table in `docs/GOLDEN_QUERY_RESULTS.md`. Also
fixed a Tavily cache-hit bug where the cached `WebVerificationResult`
retained the original caller's `facility_id` instead of the new
caller's, breaking downstream mapping when the same facility name was
verified by different callers (e.g. across test modules).**

---

## Completed

- [x] Directory structure created
- [x] `CURSOR.md` written with full project context
- [x] `requirements.txt` — stable Python 3.13-compatible packages
- [x] `.env.example` — all environment variable templates
- [x] `.gitignore` — standard Python + project-specific ignores
- [x] `agent_core/__init__.py` — package init with module list
- [x] All `agent_core/` modules created as documented placeholders
- [x] `docs/PROGRESS.md` — this file
- [x] `config/settings.py` — all spec-required env vars via pydantic-settings
  - `LOCAL_DATA_PATH`, `TAVILY_API_KEY`, `TAVILY_ENABLED`, `TAVILY_DEFAULT_DEPTH`, `TAVILY_MAX_WEB_VERIFIED`
  - `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `VECTOR_SOURCE_TABLE`, `VECTOR_SEARCH_ENDPOINT`, `VECTOR_SEARCH_INDEX`, `VECTOR_SEARCH_ENABLED`
  - `MLFLOW_ENABLED`, `MLFLOW_EXPERIMENT_NAME`
- [x] `config/settings.py` — `TRUST_CATEGORIES` and `RECOMMENDATION_READINESS_VALUES` constants
- [x] `agent_core/schemas.py` — full Pydantic models:
  - `FacilityRecord`, `AgentQuery`, `AgentIntent`, `EvidenceSnippet`
  - `ValidationFinding`, `WebVerificationResult`, `AgentRecommendation`, `AgentResponse`
  - `EvidenceBlock` retained as backward-compatibility alias for `EvidenceSnippet`
- [x] `docs/AGENT_OVERVIEW.md` — architecture, data contract, module table, fallback strategy
- [x] All tests passing (25 → 36 tests)
- [x] `agent_core/capability_taxonomy.py` — 13 capabilities with full fields, 4 helper functions
  - `Capability` TypedDict with all 9 required fields per capability
  - `get_capability()`, `list_capabilities()`, `find_capabilities_in_text()`, `get_high_acuity_capabilities()`
  - High-acuity set: ICU_CRITICAL_CARE, EMERGENCY_TRAUMA, DIALYSIS_RENAL, ONCOLOGY, NEONATAL_PEDIATRIC
- [x] `agent_core/intent_parser.py` — updated to use `find_capabilities_in_text()` and return new capability IDs
- [x] `agent_core/demo_queries.py` — updated expected_capabilities to new IDs
- [x] `tests/test_capability_taxonomy.py` — 30 new taxonomy tests
- [x] `tests/test_intent_parser.py` — expanded to 8 tests with new capability IDs
- [x] All tests passing (39 → 74 tests)
- [x] `agent_core/schemas.py` — `AgentIntent` expanded with: `original_query`, `normalized_query`, `state`, `city`, `facility_type`, `trust_preference`, `urgency`, `proximity_requested`, `web_verification_requested`, `vector_search_requested`; `raw_query` and `location` kept for backward compat
- [x] `agent_core/intent_parser.py` — `parse_query_intent()` fully implemented (pure keyword/regex, no LLM):
  - 13 Indian states/UTs + major cities detected
  - 5 facility types: hospital, clinic, doctor, pharmacy, dentist ("dental" correctly excluded from dentist detection)
  - trust_preference: trusted / verification_ok / risky_allowed / unspecified
  - urgency: emergency / urgent / routine / unspecified
  - proximity, web_verification, vector_search flags
  - min_trust_score regex extraction ("trust_score above 0.8")
  - `known_states` and `known_facility_types` parameters for caller-controlled filtering
  - `parse_intent()` kept as backward-compat wrapper
- [x] `tests/test_intent_parser.py` — rewritten: 64 tests covering all spec scenarios
- [x] All tests passing (74 → 130 tests)
- [x] `agent_core/evidence_builder.py` — fully implemented:
  - `_clean_value()` — handles None, NaN, empty, list-like strings ("['ICU']" → "ICU")
  - `build_combined_evidence(record)` — labelled text from 10 clinical fields
  - `build_evidence(facility_id, text)` — backward-compat snippet builder
  - `build_evidence_from_record(record)` — full-record snippet builder
- [x] `agent_core/vector_source_builder.py` — fully implemented:
  - `build_vector_text(record)` — pipe-delimited, embedding-optimised text; no labels, no null noise
  - `prepare_vector_source_dataframe(df)` — validates facility_id, fills defaults, builds CME and vector_text, returns 13-column canonical output
- [x] `tests/test_evidence_builder.py` — 74 new tests across 6 test classes
- [x] `docs/VECTOR_DB_PLAN.md` — full Databricks Mosaic AI Vector Search plan (schema, endpoint creation, index creation, query API, fallback strategy)
- [x] All tests passing (130 → 204 tests)
- [x] `notebooks/01_prepare_vector_source.py` — 7-cell Databricks notebook (`# COMMAND ----------` format):
  - Cell 1 setup, Cell 2 load (primary + fallback), Cell 3 select with `_safe_col()`, Cell 4 build `vector_text` UDF, Cell 5 quality checks (hard abort on null `facility_id`, soft warnings, distributions), Cell 6 idempotent Delta `saveAsTable`, Cell 7 verify
  - Output table: `workspace.default.caregrid_vector_source` (13 columns)
- [x] `docs/VECTOR_DB_PLAN.md` — rewritten with locked canonical names and full setup runbook:
  - Source table `workspace.default.caregrid_vector_source`
  - Endpoint `caregrid-vector-endpoint`
  - Index `workspace.default.caregrid_vector_index`
  - Primary key `facility_id`, text column `vector_text`, embedding model `databricks-bge-large-en`
  - 11 columns synced into the index (PK + text + 9 metadata); `combined_medical_evidence` and `evidence_summary` stay in source table
  - Sections: architecture, schema, UI + SDK endpoint creation, Delta Sync index creation, ready check, smoke-test query (with `filters_json`), env vars, fallback strategy, ops runbook, cost notes, references
  - Contains no secrets and no Databricks token
- [x] `notebooks/02_create_vector_index_notes.py` — 7-cell Databricks notebook for index provisioning:
  - Cell 1 setup + prerequisite check on source table; Cell 2 idempotent endpoint create; Cell 3 poll endpoint to ONLINE (30 min timeout); Cell 4 idempotent Delta Sync index create with `EmbeddingSourceColumn` + `columns_to_sync`; Cell 5 poll index until `ready=true` (60 min timeout); Cell 6 smoke-test semantic query + filtered query; Cell 7 env-var snippet + fallback note
  - Uses `WorkspaceClient()` runtime identity — no tokens in code
- [x] `agent_core/vector_retriever.py` — optional Databricks Mosaic AI Vector Search retriever:
  - `VectorSearchResult` (facility_id, similarity_score, metadata, source) and `VectorSearchResponse` (available, results, reason, query, source) Pydantic models
  - `VectorRetriever(settings)` with `is_available()` (cheap, no network) and `search(query, filters=None, num_results=20)`
  - Lazy import of `databricks-sdk` inside `_get_client()` — module imports cleanly without the SDK
  - **Never raises**: disabled, missing-env, missing-SDK, client-creation errors, query errors all become `available=False` with a stable `reason` code (`vector_search_disabled`, `missing_databricks_host/token/endpoint/index`, `databricks_sdk_unavailable`, `query_failed: <ExceptionType>: …`)
  - Response parser tolerates empty data, missing manifest, malformed rows, non-numeric / null scores
  - Reason strings are single-line and length-capped (200 chars) — safe for audit logging
- [x] `tests/test_vector_retriever.py` — 24 tests (rewritten from old NotImplementedError stub):
  - Schema defaults, `is_available()` paths (disabled, missing host/token/endpoint/index, fully configured)
  - Disabled `search()` returns gracefully and never calls Databricks
  - Mocked happy path: parses `manifest.columns` + `result.data_array`, extracts `facility_id` and similarity score, leaves `score` out of `metadata`
  - Verifies SDK kwargs (`index_name`, `query_text`, `columns`, `num_results`, `filters_json` JSON encoding, default `num_results=20`)
  - Error paths: SDK exception → `query_failed`, client construction error → `query_failed`, `ImportError` → `databricks_sdk_unavailable`, weird custom exception types swallowed; reason has no newlines
  - Edge cases: empty `data_array`, missing manifest, non-numeric score → 0.0, null score → 0.0, malformed-length rows skipped
  - All tests use `SimpleNamespace` settings + `unittest.mock` — never touches a real workspace
- [x] `docs/VECTOR_DB_PLAN.md` — added Section 9 “Retriever (Python Client)” with API example, model fields, reason-code table, and graceful-failure guarantees; renumbered Sections 10–13
- [x] All tests passing (204 → 227 tests)
- [x] `agent_core/local_retriever.py` — in-memory pandas fallback retriever:
  - `LocalCandidate` Pydantic model: `facility_id`, `raw_record`, `matched_fields`, `matched_capabilities`, `local_relevance_score`, `relaxation_notes`
  - `retrieve_local_candidates(df, intent, limit_pool=200, *, allow_state_relaxation=False)` — strict filter → cascading relaxation → capability scoring → rank → truncate
  - Strict filter: `state` (case-insensitive eq), `facility_type` (ci eq), `min_trust_score` (>=); each step silently no-ops when the column is missing from the source DataFrame
  - Cascading relaxation when strict result is empty: drop `min_trust_score`, then drop `facility_type`; **never** drop `state` unless `allow_state_relaxation=True`. Each relaxation step is logged onto `relaxation_notes` (e.g. `"relaxed min_trust_score (was 0.99)"`)
  - Scoring: counts `(term, field)` hits across the 6 search columns (`specialties`, `procedures`, `equipment`, `capabilities_raw`, `evidence_summary`, `combined_medical_evidence`); weights = keyword 1.0 / synonym 1.0 / strong_evidence 2.0 + 0.5 capability bonus; per-capability term lists are deduped to keep the largest weight
  - Free-form fallback: when `intent.capabilities_required` is empty, scores against query tokens (length ≥ 4) so the retriever stays useful
  - Robust to NaN / null-ish cells (`"none"`, `"nan"`, `"null"`, `"n/a"`, `"<na>"`, `"[]"`) and to partial schemas (only `facility_id` is truly required)
  - Ranking: `local_relevance_score` desc, `trust_score` desc tiebreaker, then truncated to `limit_pool`
  - `retrieve_local(query, df, top_k)` legacy single-string keyword filter retained for backward compatibility
- [x] `tests/test_local_retriever.py` — 20 tests (3 legacy + 17 new):
  - Required spec scenarios: ICU query returns Apollo + Sketchy with `ICU_CRITICAL_CARE`; dialysis query returns Fortis with hits across `procedures` + `equipment`; Maharashtra hospital query returns only Maharashtra hospitals (excludes Karnataka rows and Maharashtra clinic); relaxation cascade records `relaxed min_trust_score (was 0.99)` and `relaxed facility_type (was hospital)` notes
  - State guard: zero matches in Kerala returns `[]` by default; opting into `allow_state_relaxation=True` relaxes and notes it
  - Both relaxations stack when needed (trust first, then facility_type)
  - Ranking is monotonically descending; `limit_pool` is respected; empty DataFrame → `[]`
  - Robustness: missing optional columns, NaN cells, no-capability free-form queries, per-candidate (not shared) `relaxation_notes` lists
- [x] All tests passing (227 → 244 tests)
- [x] `agent_core/schemas.py` — `EvidenceSnippet` extended (backward-compatible) with optional `support_level: str = "weak"`, `capability_id: Optional[str] = None`, `matched_terms: list[str] = []`; docstring documents the four allowed levels (`strong` / `moderate` / `weak` / `contradiction`, with `contradiction` reserved for `contradiction_rules.py`)
- [x] `agent_core/evidence_citation.py` — `extract_evidence_snippets(record, requested_capabilities)`:
  - Constants: `SUPPORT_STRONG/MODERATE/WEAK/CONTRADICTION`, `EVIDENCE_SUPPORT_LEVELS`, `EVIDENCE_FIELDS_PRIORITY` (6 fields), `MAX_SNIPPETS_PER_CAPABILITY=3`, `MAX_EXCERPT_LENGTH=240`
  - Six search fields scanned in priority order: `equipment` → `procedures` → `specialties` → `capabilities_raw` → `evidence_summary` → `combined_medical_evidence`
  - Per capability: gathers (strong, regular) terms from the taxonomy — `strong_evidence_keywords` are strong; `keywords + synonyms + supporting_equipment` are regular (with strong terms removed from regular to avoid double-counting); both lists sorted longest-first so the longest match wins
  - Segment splitter on `.`, `;`, `\n`, `|` (preserves `C-arm`, `T-cell`); collapses whitespace; truncates excerpts at 240 chars with whole-word boundary + ellipsis
  - Support-level rules: any strong term in any field → `strong`; regular term in equipment/procedures → `strong`; regular term in specialties/capabilities_raw → `moderate`; regular term in evidence_summary/combined_medical_evidence → `weak`
  - Per-capability cap of 3 snippets, ranked by `(support_level, field_priority)`, deduped by lowercased excerpt
  - Robust to NaN, null-ish strings (`"none"`, `"nan"`, `"null"`, `"n/a"`, `"<na>"`), and python-list-looking strings (`"['ICU','Dialysis']"` → `"ICU, Dialysis"`)
  - Unknown capability IDs and empty inputs (record / capability list) return safely
  - `format_citations()` legacy renderer preserved
- [x] `tests/test_evidence_citation.py` — 25 tests (3 legacy preserved + 22 new):
  - Module surface: support-level constants, 6-field priority, max-3 cap
  - Required spec: ICU + ventilator → strong; dialysis machine → strong; oncology with only "cancer" in specialties → moderate, in broad text → weak; no evidence → `[]`; long evidence → ≤240 chars + `...`
  - Ranking + dedupe: max 3 per capability honoured even with 4+ candidate hits; strong outranks weak; field priority breaks ties within a level (equipment > procedures); duplicate excerpts collapsed
  - Multiple capabilities: per-capability bundles in input order; unknown capability IDs silently skipped
  - Schema fields populated correctly; `relevance_score` = 1.0 / 0.6 / 0.3 for strong / moderate / weak
  - Robustness: empty record, empty capability list, NaN / null-ish cells, list-like string unwrap, segment splitter handles `\n` + `|`
- [x] All tests passing (244 → 266 tests)
- [x] `agent_core/schemas.py` — `ValidationFinding` extended (backward-compatible) with optional `capability`, `finding_type`, `evidence_used: list[str] = []`, `missing_evidence: list[str] = []`, `recommendation_impact: str = "none"`; severity scale documented as `info` / `low` / `medium` / `high` (legacy `warning` / `error` still accepted)
- [x] `agent_core/contradiction_rules.py` — rewritten against the real `TRUST_CATEGORIES` and `RECOMMENDATION_READINESS_VALUES` from `config/settings.py`:
  - 5 rules: `CR_HIGH_SCORE_LOW_TRUST_CATEGORY`, `CR_LOW_SCORE_HIGH_TRUST_CATEGORY`, `CR_READY_BUT_LOW_SCORE`, `CR_DO_NOT_RECOMMEND_BUT_HIGH_SCORE`, `CR_MISSING_TRUST_CATEGORY` — each with `id`, `description`, `severity`, `check`
  - `find_contradictions(record)` returns the rich dicts the validator uses; `check_contradictions(record)` retained for backward compatibility (returns IDs only); `get_rule(rule_id)` lookup helper
  - Coerces non-numeric `trust_score`s safely (`_safe_float`) and treats missing fields as null — never raises on bad input
- [x] `agent_core/validator.py` — `validate_candidate(record, requested_capabilities, evidence_snippets) -> list[ValidationFinding]`:
  - Six per-capability rule sets in `VALIDATION_RULES` covering exactly the capabilities specified in the prompt: `ICU_CRITICAL_CARE`, `SURGERY`, `DIALYSIS_RENAL`, `ONCOLOGY`, `EMERGENCY_TRAUMA`, `NEONATAL_PEDIATRIC` (each rule has `rule_id`, `display_name`, `required_evidence_terms`)
  - Decision matrix: any strong snippet → `supported` / `info` / `none`; only weak/moderate snippets *or* terms found in record without a snippet → `weak_evidence` / `medium` / `downgrade_to_verify_before_use`; nothing at all → `missing_evidence` / `high` / `do_not_recommend`
  - `evidence_used` carries up to 3 supporting snippet excerpts; `missing_evidence` lists up to 6 expected terms not found in the record
  - Term presence check uses case-insensitive substring search, with word-boundary matching for short tokens (≤3 chars) and digit/`/`/`x`-only tokens — so bare `OT` matches `modular OT` but not `rotor`, and `24/7` doesn't false-match inside dates
  - Record search blob covers 8 fields: `name`, `specialties`, `procedures`, `equipment`, `capabilities_raw`, `evidence_summary`, `combined_medical_evidence`, `required_staff` — null/NaN/`"None"`-style values are silently dropped
  - Capabilities not in the 6-rule set are silently skipped (validator is opt-in by design); duplicate requested capabilities are deduped while preserving order
  - Contradictions from `find_contradictions(record)` are appended after capability findings as `finding_type=contradiction` / `recommendation_impact=flag_for_review`
  - Stable string constants exported (`FINDING_*`, `IMPACT_*`, `SEVERITY_*`) for use by callers / tests
  - `validate_response(response)` retained for backward compatibility with the original Stage-1 response-level sanity check
- [x] `tests/test_validator.py` — 27 tests (2 legacy preserved + 25 new):
  - Required spec scenarios: ICU claim without equipment → high severity + `do_not_recommend`; Surgery without OT/anaesthesia → high severity finding; Dialysis with `dialysis machine` + strong snippet → `supported` / `info` / `none`; Emergency with ambulance + 24/7 + strong snippet → `supported` / `info` / `none`
  - Other validator paths: weak-only snippets → `weak_evidence` / `medium`; terms-in-record but no snippets → `weak_evidence` / `medium`; strong outranks weak when both present; neonatal happy path with incubator
  - Edge cases: empty `requested_capabilities` → `[]`; unknown capability silently skipped; empty record → `[]`; multiple capabilities produce one finding each; duplicate caps deduped; NaN / `None` / `"None"` cells tolerated; OT word-boundary positive + negative cases (rotor not matched, modular OT matched)
  - Schema invariants: every finding has populated `facility_id` / `capability` / `finding_type` / `severity` / `message`; `recommendation_impact` is one of the four allowed values; `VALIDATION_RULES` covers exactly the 6 spec'd capabilities
  - Contradictions: high score + low trust category, ready-but-low-score, contradictions appear after capability findings, clean record produces no findings, `check_contradictions()` returns string IDs, `find_contradictions()` returns dicts with severity, `get_rule()` lookup, empty record safe
- [x] All tests passing (266 → 291 tests)
- [x] `agent_core/schemas.py` — `WebVerificationResult` extended (backward-compatible) with optional `web_checked`, `web_available`, `matched_name`, `matched_location`, `matched_capability: list[str]`, `top_url`, `top_snippet`, `verification_score: float`, `verification_status: str` (default `"skipped"`), `verification_notes: list[str]`, `error_message: Optional[str]`, `credits_estimated: Optional[int]`. The status vocabulary (`verified` / `partial` / `unverified` / `skipped` / `error`) is documented on the model
- [x] `agent_core/tavily_cache.py` — rewritten as a thread-safe in-memory TTL cache:
  - `TavilyCache(ttl_seconds=24*3600)` with `get` / `set` / `invalidate` / `clear` / `size` / `ttl_seconds`
  - `TavilyCache.make_key(facility_name, city, state, capabilities, depth)` — deterministic key, capability list normalised (lowercased, deduped, sorted) so `["ICU","dialysis"]` and `["dialysis","ICU"]` collide; depth is part of the key so `basic` and `advanced` cache separately
  - Lazy expiry on access — no background sweeper
  - Module singleton via `get_default_cache()`; `reset_default_cache(ttl_seconds)` for tests
  - Legacy `load_cache(facility_id)` / `save_cache(facility_id, result)` file helpers preserved for backward compat (now also tolerant of OS / JSON errors instead of crashing the agent)
- [x] `agent_core/tavily_verifier.py` — Tavily integration with strict graceful-degradation contract:
  - `verify_facility_web_presence(facility_name, city, state, requested_capabilities, depth, *, facility_id, settings, cache, client_factory)` — single-facility verification; never raises; reads `TAVILY_*` from `config.settings.settings` unless overridden
  - `verify_top_recommendations(recommendations, max_to_verify, depth, *, city, state, requested_capabilities, settings, cache, client_factory)` — verifies the first N recommendations; accepts both `AgentRecommendation` objects and plain dicts; per-item `city`/`state` override function defaults
  - Three depth modes: `basic` (1 search, 1 credit), `advanced` (facility + capability search if caps given, 2 advanced calls = 4 credits), `demo` (advanced + best-effort official-URL extraction); unknown depth strings fall back to `basic`
  - Lazy import of `tavily-python` inside `_default_client_factory(api_key)`; tests inject a `MagicMock` factory and the SDK is never imported in CI
  - **Never raises**: disabled / missing-key → `verification_status="skipped"` (no client construction); SDK missing → `tavily_sdk_unavailable`; client construction or `client.search()` errors → `tavily_api_error` with single-line, ≤200-char `error_message`; malformed Tavily payloads (`"not a dict"`, missing keys) treated as zero results, not as exceptions
  - Scoring rubric: name 0.4, city 0.2, state 0.1, capability hits 0.2 × hit-ratio, demo +0.1 for an official-looking URL; status thresholds `>=0.7` → `verified`, `[0.4,0.7)` → `partial`, `<0.4` → `unverified`
  - "Official URL" heuristic in `demo` skips aggregator domains (`justdial.com`, `practo.com`, `lybrate.com`, `facebook.com`, `instagram.com`, `wikipedia.org`, `youtube.com`, `google.com`, etc.) and prefers a host whose name overlaps with a slug derived from the facility name
  - Results are cached by `TavilyCache.make_key`; cache hits return a copy with `cached=True`. **Errors are never cached** so a transient failure does not poison subsequent retries
  - Stable string constants exported (`VERIFICATION_*`, `REASON_*`, `DEPTH_*`, `ALLOWED_DEPTHS`) for use by callers / tests
  - `verify_facility(facility_name, api_key)` retained as a backward-compat shim that synthesises a fake settings object — old test contract (no NotImplementedError) replaced; if `api_key` is empty the shim returns a `skipped` result, otherwise it forwards to the new path
- [x] `tests/test_tavily_verifier.py` — 34 tests (rewritten from the old NotImplementedError stub):
  - Required spec scenarios: missing API key → no crash, returns `skipped`; mocked successful search → fields mapped (`facility_id`, `matched_name`, `matched_location`, `matched_capability`, `top_url`, `top_snippet`, `verification_score`, `verification_status`, `credits_estimated`); cache prevents the second identical call; `max_to_verify=2` produces exactly 2 results from a 5-rec list; depth respected (1 vs 2 calls, `search_depth` kwarg correct, advanced query includes capability tokens)
  - Disabled path (`TAVILY_ENABLED=false`) and missing-key path both return `skipped` and **never invoke** the client factory
  - Unknown depth string falls back to `basic`; partial-match-only-name maps to `partial`; results without any match map to `unverified`; empty results return `unverified` with `web_available=True` (call did happen, just no hits)
  - Cache: TTL expiry forces a fresh call after the window; key normalises capability ordering (`["ICU","dialysis"]` ≡ `["dialysis","ICU"]`); cache key distinguishes by depth and by capability content; errors are not cached
  - Error paths: `client_factory` raising `ImportError` → `tavily_sdk_unavailable`; other client construction error → `tavily_api_error` with `RuntimeError:` prefix; `client.search` raising → `tavily_api_error` with single-line, ≤200-char message; Tavily returning a non-dict (e.g. `"not a dict"`) → `unverified`, no exception
  - `verify_top_recommendations`: works with `AgentRecommendation`-style objects and with dicts; per-item `city`/`state` overrides flow through to the actual Tavily query string; empty recommendation list returns `[]`; `max_to_verify=0` returns `[]` and never calls the factory; disabled settings return per-recommendation `skipped` results
  - Schema: `WebVerificationResult(facility_id="X")` defaults are safe; all 12 new fields are populated on the success path; `verification_status` is always one of the 5 documented values
  - Backward-compat: legacy `verify_facility(name, api_key="")` returns a `skipped` `WebVerificationResult`
- [x] `docs/TAVILY_PLAN.md` — full Tavily plan: when to enable, public API, depth modes, scoring rubric, schema field-by-field reference, cache semantics, env vars, failure-mode table, recommendation-engine integration sketch, cost notes, test contract; contains no secrets
- [x] All tests passing (291 → 324 tests; the original `test_tavily_verifier_raises_not_implemented` stub test was removed since the function is now implemented, then 34 new verifier tests were added)
- [x] `agent_core/schemas.py` — extended for the final response contract:
  - New `ScoreBreakdown` model with all 9 components: `trust_score_component`, `readiness_component`, `capability_match_component`, `evidence_strength_component`, `validation_penalty`, `warning_penalty`, `vector_similarity_component`, `tavily_verification_component`, `final_score` (clipped to `[0,1]`)
  - `AgentRecommendation` extended (backward-compatible) with `facility_type`, `city`, `state`, `matched_capabilities`, `matched_fields`, `validation_findings: list[ValidationFinding]`, `warning_flags`, `score_breakdown: Optional[ScoreBreakdown]`, `reason_for_recommendation: str`, `human_next_steps: list[str]`
  - `AgentResponse` extended (backward-compatible) with `interpreted_intent: Optional[AgentIntent]`, `retrieval_summary: dict`, `total_candidates: int`, `returned: int`, `fallback_message: str`, `trace_summary: dict`; the original `intent`, `evidence`, `warnings`, `validation_findings` fields are preserved
- [x] `agent_core/audit_logger.py` — append-only audit logger:
  - `AuditLogger(log_path=None, *, persist=True, settings=None)` class with thread-safe `log(event_type, payload, *, persist=None)`, `get_events()`, `event_types()`, `to_summary()`, `clear()`, `__len__`
  - Two modes: in-memory only (tests, scripts) and in-memory + JSONL append (default `data/outputs/audit_log.jsonl`); IO errors are swallowed so logging cannot crash the agent
  - Module singleton via `get_default_audit_logger()` / `reset_default_audit_logger(...)`; legacy `log_event(event, log_path)` retained for backward compat
  - `to_summary()` returns `{total_events, event_type_counts, first_event_at, last_event_at}` for embedding into `trace_summary`
- [x] `agent_core/recommendation_engine.py` — full pipeline orchestrator:
  - `run_recommendation(query, facilities_df, state=None, facility_type=None, min_trust_score=None, max_results=5, enable_vector_search=False, enable_web_verification=False, web_verification_depth="basic", max_web_verified=3, *, settings=None, vector_retriever=None, tavily_cache=None, tavily_client_factory=None, audit_logger=None) -> AgentResponse`
  - 9-stage pipeline: parse intent → apply caller overrides → local retrieval → (optional) vector retrieval → merge by `facility_id` → extract evidence snippets → validate capabilities → score (9 components) → sort + truncate to `max_results` → (optional) Tavily verify top `max_web_verified` and re-sort → build `AgentResponse`
  - Score weights: trust 0.25, readiness 0.15, capability_match 0.15, evidence 0.15, vector 0.15, tavily 0.15; penalties contradiction -0.15, missing/high -0.10, weak/medium -0.05, per-warning -0.02; final_score clipped to `[0,1]`
  - Readiness mapping: `Ready for recommendation` → 1.0, `Usable with verification` → 0.5, `Do not recommend without human review` / unset → 0.0 (multiplied by `_W_READINESS=0.15`)
  - Evidence strength weights: `strong=1.0`, `moderate=0.6`, `weak=0.3`, `contradiction=0.0` (mean across snippets × `_W_EVIDENCE=0.15`)
  - Reason-for-recommendation generator describes which factors drove the rank (matched caps, strong-snippet count, trust category, vector similarity, web verification); `human_next_steps` builder differentiates by validation severity, web-verification status, and emergency urgency
  - **Never raises**: each stage (intent parse, local retrieval, vector call, merge, snippet extraction, validation, scoring, Tavily) is wrapped in a try/except that records the error onto `trace_summary["errors"]` and degrades to last-known-good state
  - Vector handling: when `enable_vector_search=False` the Databricks SDK is never imported; when enabled but the retriever reports `available=False` the engine logs the reason and continues with local-only candidates; vector hits not in the local pool are looked up in the source DataFrame (or the hit's metadata as a last-resort record)
  - Tavily handling: when `enable_web_verification=False` no calls are made; when enabled the engine builds a thin payload list (flat name/city/state/caps) so `verify_top_recommendations` works correctly; web score adds `tavily_verification_component` to the existing breakdown and the top-K is re-sorted
  - `retrieval_summary` exposes `local_count`, `vector_enabled`, `vector_available`, `vector_count`, `vector_reason`, `merged_count`, `after_top_k_count`, `relaxation_used`
  - `trace_summary` exposes ordered `stages`, `errors`, `audit_log` snapshot, and per-subsystem `tavily` / `vector` blocks
  - Constant `SAFETY_NOTE` is set on every response, including empty / fallback / exception paths
  - `fallback_message` is populated only when `recommendations == []` and lists which filters were tried + suggests relaxations
  - Original `recommend(df, trust_score_threshold, top_k)` Stage-1 ranker preserved for backward compatibility
- [x] `tests/test_recommendation_engine.py` — 33 tests (3 legacy `recommend()` tests preserved + 30 new):
  - Required spec scenarios: trusted ICU query returns a structured response with the strongest-evidence facility on top; dialysis query returns Karnataka result; no-match query returns a populated `fallback_message`; `safety_note` is set on success / fallback / blank-query paths; validation findings lower the score (ICU-claim-without-equipment ranks below ICU-with-equipment and carries a non-zero `validation_penalty`); Tavily disabled path produces no `web_verification` and zero `tavily_verification_component`; mocked Tavily-enabled path attaches a `WebVerificationResult` to the top recommendation, increments `trace_summary["tavily"]["verified"]`, and contributes to `final_score`; vector disabled path skips the stage entirely; mocked vector path boosts the matching candidate by `vector_similarity_component`
  - Response / recommendation contracts: `AgentResponse` carries all 11 required fields (`query`, `intent`, `interpreted_intent`, `recommendations`, `reasoning`, `safety_note`, `fallback_message`, `trace_summary`, `retrieval_summary`, `total_candidates`, `returned`); every recommendation carries all 17 required fields (`facility_id`, `name`, `facility_type`, `city`, `state`, `trust_score`, `trust_category`, `recommendation_readiness`, `matched_capabilities`, `matched_fields`, `evidence_snippets`, `validation_findings`, `warning_flags`, `web_verification`, `score_breakdown`, `reason_for_recommendation`, `human_next_steps`)
  - Score breakdown: components are individually populated, all in `[0,1]`, vector / Tavily zero on default path
  - Override semantics: `max_results` truncates; `min_trust_score` and `facility_type` overrides apply to the recommendations
  - Tavily: `max_web_verified=0` skips all calls; `max_web_verified=1` produces ≤1 verified result
  - Vector: unavailable response is silently absorbed (no crash, local results flow through); a vector-only candidate (not in local pool but present in DataFrame) gets added; an exception in the retriever is caught and appears under `trace_summary["errors"]`
  - Audit logger: receives all 8 pipeline events (`intent_parsed`, `local_retrieval`, `vector_retrieval`, `merge`, `enrich`, `score_and_rank`, `tavily_verification`, `final_response`); `to_summary()` snapshot embedded into `trace_summary` matches `len(logger)` (off-by-one tolerated since the snapshot is taken just before the final-response event); pipeline still works when no logger is supplied
  - Robustness: empty DataFrame / blank query / `parse_query_intent` raising / `retrieve_local_candidates` raising / `extract_evidence_snippets` raising — all caught, no crash, errors recorded on the trace
  - Reasoning includes the top-result's name; every recommendation's `human_next_steps` is non-empty; emergency wording is at least partially exercised
  - 3 legacy `recommend()` tests still pass against the preserved Stage-1 API
- [x] All tests passing (324 → 354 tests; +30 new orchestrator tests, original 3 `recommend()` tests preserved in the same module)
- [x] `agent_core/demo_queries.py` — extended with `GOLDEN_QUERIES` (10 curated entries with `id`, `query`, `expected_capabilities`, `expected_state`, `expected_facility_type`, `expected_trust_preference`, `expected_urgency`, `expected_behavior`, `notes`); the original Stage-3 `DEMO_QUERIES` (5 entries) is preserved verbatim so the legacy intent-parser tests keep working
- [x] `tests/test_golden_queries.py` — full evaluation suite (60 tests):
  - Shared 11-row fixture DataFrame with one or two facilities per golden query plus two "sentinel" rows (`F-VER-01` for verification-readiness coverage, `F-RISKY-01` for unsupported-emergency-claim coverage)
  - Universal contract test (parametrized × 10): `AgentResponse` is well-formed, `interpreted_intent` populated, `safety_note` constant set, recommendations OR `fallback_message` present, every recommendation has a populated `ScoreBreakdown` with `final_score ∈ [0,1]`, state filter respected, facility_type filter respected (with `retrieved_via_relaxation` escape hatch), reason + human_next_steps non-empty
  - Intent extraction test (parametrized × 10): expected capabilities are a subset of the parser output (tolerates the parser's known substring over-extraction on short tokens like `"OR"`/`"ER"`); state, facility_type, trust_preference, urgency are exact-match
  - Evidence snippet test (parametrized × 10): top recommendation carries an evidence snippet for at least one expected capability (with the relaxation escape hatch)
  - Per-query targeted tests for all 10 queries (top-3 trust ranking for GQ-001; Bihar-only enforcement for GQ-002; trauma-centre-on-top + emergency next-step for GQ-003; UP dialysis + state-strict for GQ-004; oncology snippet on top for GQ-005; TN maternity hospital on top for GQ-006; Gujarat NICU + multi-capability evidence for GQ-007; Delhi diagnostics for GQ-008; verification-readiness surfacing for GQ-009; missing-evidence + warning_flag for GQ-010)
  - Mocked-Tavily smoke test (parametrized × 10): `enable_web_verification=True` + `client_factory=MagicMock` — confirms `trace_summary["tavily"]["enabled"]` is True, no real network traffic, every verified recommendation gets a `WebVerificationResult` whose `verification_status` is one of the documented values
  - Aggregate sanity: 10 entries, unique IDs, all required keys present
  - Backward-compat: original 8 `DEMO_QUERIES` tests preserved verbatim
- [x] `agent_core/tavily_verifier.py` — bug fix: on cache hit, the returned `WebVerificationResult.facility_id` is now overridden with the *caller's* `facility_id` instead of being silently inherited from whoever wrote the cache entry. Without this fix, two different `AgentRecommendation`s pointing at the same facility name could collide on the cache and the engine would map the verification result to the wrong recommendation. Surfaced by golden-query / engine cross-test pollution.
- [x] `tests/test_tavily_verifier.py` — new regression test `test_cache_hit_overrides_facility_id_with_caller_value` documents the fix
- [x] `docs/GOLDEN_QUERY_RESULTS.md` — human-readable report with a fixture table, the full 10-query evaluation table (query / expected intent / expected behavior / test status / notes), the universal-contract checklist, the mocked-Tavily test description, instructions for running the suite, and a "known parser gaps" section that documents the substring over-extraction (e.g. "ER" in "centers") and the missing `"need human verification"` trigger
- [x] All tests passing (354 → 407 tests; +60 new golden-query tests, +1 cache regression test, +0 changes to the 354 prior tests)
- [x] `config/settings.py` — dual env-var name compatibility via `pydantic.AliasChoices`. `tavily_enabled` reads `TAVILY_ENABLED` *or* `ENABLE_TAVILY`; `tavily_max_web_verified` reads `TAVILY_MAX_WEB_VERIFIED` *or* `TAVILY_MAX_RESULTS`; `vector_search_enabled` reads `VECTOR_SEARCH_ENABLED` *or* `ENABLE_VECTOR_SEARCH`; `vector_search_endpoint` reads `VECTOR_SEARCH_ENDPOINT` *or* `DATABRICKS_VECTOR_SEARCH_ENDPOINT`; `vector_search_index` reads `VECTOR_SEARCH_INDEX` *or* `DATABRICKS_VECTOR_INDEX_NAME`. `populate_by_name=True` so unit tests can still pass field names directly.
- [x] `tests/test_settings.py` — 11 new alias tests covering both naming styles for every dual-name field, plus an isolation fix for `test_settings_defaults` (it now disables `_env_file` and clears alias env vars so the local developer `.env` doesn't leak into the defaults assertion)
- [x] `.env.example` — rewritten to document both naming styles side-by-side with comments explaining which is canonical and that either flag enables the feature
- [x] Local `.env` created (gitignored via `.gitignore` `.env` rule) with a real Tavily API key, `ENABLE_TAVILY=true`, `TAVILY_DEFAULT_DEPTH=basic`, `TAVILY_MAX_RESULTS=2`, `ENABLE_VECTOR_SEARCH=false`. **Note: the key was visible in the chat transcript and should be rotated before any wider distribution.**
- [x] Live Tavily smoke check — single call against `Apollo Hospitals, Mumbai, Maharashtra` returned `verification_status="verified"`, `verification_score=0.7`, real public URL + snippet. End-to-end wiring confirmed; smoke script removed after the run (not part of pytest)
- [x] All tests passing (407 → 419 tests; +11 new alias tests, +1 isolation fix on the existing defaults test)
- [x] `run_agent_demo.py` — Stage 15 smoke-test runner against the real 10k CSV:
  - Public functions: `load_real_dataset(path)`, `validate_real_dataset(df)`, `get_default_demo_queries()`, `run_demo_queries(queries, df, *, max_results, enable_tavily, enable_vector, web_depth, max_web_verified)`, `save_json_output(results, path)`, `save_markdown_report(results, path)`
  - 5 default queries exactly matching the spec (Bihar ICU, Maharashtra emergency, UP dialysis, Gujarat oncology, TN maternity)
  - CLI flags: `--query`, `--max-results`, `--enable-tavily`, `--enable-vector`, `--web-depth {basic,advanced,demo}`, `--max-web-verified`, `--dataset-path`, `--output-json`, `--output-md`
  - Defaults: `enable_tavily=False`, `enable_vector=False`, `max_results=5`, `web_depth=basic`, `max_web_verified=2`, JSON → `data/outputs/demo_agent_results.json`, Markdown → `data/outputs/demo_agent_results.md`
  - Markdown report per query: Interpreted Intent, Retrieval Summary, Top Recommendations table (rank/name/city/state/facility_type/trust_score/trust_category/recommendation_readiness/final_score), Evidence Snippets, Validation Findings, Warning Flags, Tavily Verification (with web_checked/web_available/status/score/top_url/top_snippet/credits), Safety Note
  - Missing CSV → exit code 2 with clear stderr message; missing required columns → exit code 2 listing the offenders; never raises a Python traceback
  - Unknown `--web-depth` falls back to `basic` with a console warning instead of crashing
  - Live console output for the 5-default run on the real CSV: 10k rows, 34 states, all 5 queries returned 5 recommendations each, totals on Bihar/Maharashtra/UP/Gujarat/TN; durations 0.09s–0.62s per query
- [x] `tests/test_run_agent_demo.py` — 21 new tests:
  - Module surface: imports cleanly, `REQUIRED_COLUMNS` complete, every public function exposed
  - `get_default_demo_queries()` returns exactly 5, exact contents, returns a fresh copy (caller mutation safe)
  - `validate_real_dataset()` passes on a complete tiny DataFrame, exits 2 on missing required columns, exits 2 on `None`
  - `load_real_dataset()` exits 2 on a missing file, reads a temp CSV correctly
  - `save_json_output()` writes a file, creates nested parent dirs, serialises `AgentResponse` via `model_dump(mode="json")` so `safety_note` and `recommendations` survive round-trip
  - `save_markdown_report()` writes a file, includes the query text + every required section header, handles an empty results list
  - Network isolation: `test_run_demo_queries_default_does_not_call_tavily` mocks `_default_client_factory` and asserts not called; `test_run_demo_queries_default_does_not_call_databricks` mocks `_build_default_vector_retriever` to raise on use and asserts no call
  - `run_demo_queries()` returns proper `AgentResponse` objects (not dicts), unknown depth falls back to basic
  - CLI surface: `--help` exits 0 with the expected flag list, `main()` end-to-end with a tiny CSV writes both JSON and Markdown
- [x] `docs/TAVILY_REAL_SMOKE_TEST.md` — full Tavily smoke runbook: prerequisites, `.env` configuration (both naming styles documented side-by-side), local-only sanity check command, exact Tavily smoke command, expected result fields table, four independent ways to confirm the call was real (URL reachable, snippet content, credit counter movement, dashboard view), credit safety rules, troubleshooting matrix
- [x] `docs/REAL_INTEGRATION_RUNBOOK.md` — operator runbook: where the CSV goes, required columns, local-only run command, Tavily-enabled run command, vector-enabled run command (incl. `trace_summary["vector"]` shape for confirmation), output file inventory, troubleshooting matrix, explicit list of "what the runner deliberately does NOT do" (no per-facility Tavily, no Databricks unless explicitly enabled, no source CSV mutation, no secret persistence outside `.env`)
- [x] All tests passing (419 → 440 tests; +21 new runner tests, no regressions)
- [x] Live demo run against the real 10k CSV — all 5 default queries succeeded; outputs written to `data/outputs/demo_agent_results.{json,md}`; Tavily disabled, Vector disabled, no external calls
- [x] `agent_core/capability_taxonomy.py` — Stage 16 safe matching foundation:
  - `normalize_text(text)` — lowercase + collapse whitespace; treats `None` as `""`
  - `term_matches(text, term)` — case-insensitive phrase containment; for short terms (≤ 3 chars) or terms containing `0-9 / x : &`, falls back to a compiled regex with `(?<![a-z0-9])` / `(?![a-z0-9])` boundaries so `"ER"` does **not** match inside `"centers"`, `"OT"` does **not** match inside `"support"`, `"24/7"` matches but `"24x7"` is treated as a separate (also-handled) term
  - `find_matching_terms(text, terms)` — returns matched terms in **input order**, deduped, never raises on `None` / non-iterables
  - `find_capabilities_in_text()` rewired to use `find_matching_terms()` so every downstream caller inherits the safe behaviour automatically
- [x] `agent_core/capability_taxonomy.py` — `EMERGENCY_TRAUMA` capability tightened:
  - `strong_evidence_keywords` restricted to clinically meaningful phrases: `emergency department`, `emergency room`, `casualty`, `trauma centre`, `trauma center`, `ambulance`, `24/7`, `24x7`, `ventilator`, `triage`, `resuscitation`, `crash cart`
  - Generic terms (`surgery`, `treatment`, `oxygen`, `critical support`) removed from strong evidence so they no longer satisfy emergency validation by themselves
  - `keywords` retained `"er"` / `"a&e"` but now relies on the new word-boundary matcher
- [x] `agent_core/capability_taxonomy.py` — `DIALYSIS_RENAL` capability tightened:
  - Bare `"kidney"` and `"renal"` removed (they were matching `"kidney stones"`, `"adrenal"`, etc.)
  - Strong evidence: `haemodialysis`, `hemodialysis`, `dialysis machine`, `dialyzer`, `AV fistula`, `peritoneal dialysis`, `CRRT`, `nephrology unit`
  - Moderate evidence: `nephrologist`, `kidney transplant`, `renal replacement therapy`
- [x] `agent_core/evidence_citation.py` — internal `_find_terms()` now delegates to `find_matching_terms()`; `"Stapler Circumcision"` no longer produces an `EMERGENCY_TRAUMA` evidence snippet; `"kidney stones"` no longer produces a `DIALYSIS_RENAL` evidence snippet
- [x] `agent_core/validator.py` — internal `_term_present()` now delegates to `term_matches()`; `EMERGENCY_TRAUMA` `required_evidence_terms` updated to clinical-only (`emergency`, `casualty`, `trauma`, `ambulance`, `ventilator`, `critical care`, `triage`, `ER`, `A&E`); `DIALYSIS_RENAL` `required_evidence_terms` aligned with the tightened taxonomy (`haemodialysis machine`, `nephrologist`, `AV fistula`, `peritoneal dialysis`, `CRRT`)
- [x] `agent_core/intent_parser.py` — implicitly fixed: `"Find dialysis centers in Uttar Pradesh"` now detects `DIALYSIS_RENAL` only (no false `EMERGENCY_TRAUMA` from `"centers"` containing `"ER"`); benefits from the upstream `find_capabilities_in_text()` rewiring
- [x] `agent_core/local_retriever.py` — Stage 16 ranking fixes:
  - All term containment checks routed through `term_matches()`; `find_matching_terms()` used for capability scanning
  - New `WEIGHT_NAME_MATCH = 3.0` constant
  - `_score_row()` extended with a `name_text` argument; if any keyword or synonym for a requested capability appears in the facility's name (e.g. `"Lucknow Dialysis Centre"`), the facility gets the name-match bonus on top of its field-hit score
  - `retrieve_local_candidates()` extracts `name_text` once per row and passes it through to `_score_row()`
- [x] `agent_core/recommendation_engine.py` — Stage 16 scoring + Tavily interpretation:
  - New 9th score component: `_W_LOCAL_RELEVANCE = 0.10`, `_LOCAL_RELEVANCE_SAT = 15.0`; `local_score / SAT` is clamped to `[0,1]` and weighted into the final score, then folded into `capability_match_component` for backward-compatibility on the breakdown
  - This change is what allows the dedicated trauma centre to outrank a generic high-trust multispeciality hospital on the Maharashtra emergency golden query
  - `_build_reason_for_recommendation()`: when Tavily `verification_status="verified"` but `matched_capability=[]`, the reason now reads "web-verified identity/location only — clinical capability not confirmed online" instead of falsely implying clinical confirmation; when `matched_capability` is non-empty, the verified capabilities are listed
  - `_build_human_next_steps()`: adds an explicit step on the verified-but-no-capability branch — "Web verification confirmed identity/location only — call the facility directly to confirm the clinical capability (equipment, staff, on-site availability)."
- [x] `agent_core/contradiction_rules.py` — new high-acuity claim rule:
  - `_HIGH_ACUITY_CLAIM_TERMS` covers emergency / trauma / ICU / dialysis / critical care
  - `_claims_high_acuity(record)` scans `specialties` and `capabilities_raw`
  - `_is_blank(value)` treats null / empty list / empty string / `"[]"` / `"None"` as blank
  - `CR_HIGH_ACUITY_CLAIM_NO_EVIDENCE` (severity `high`) fires when a high-acuity claim is present in `specialties` or `capabilities_raw` but **both** `equipment` and `procedures` are blank — closes the GQ-010 sketchy-hospital loophole so the recommendation comes back with `recommendation_readiness="missing_evidence"` and a populated warning flag
- [x] `tests/test_clinical_matching_quality.py` — new regression suite (23 tests):
  - Helpers: `normalize_text` / `term_matches` (with explicit cases for `"ER"` not in `"centers"`, `"OT"` not in `"support"`, `"OR"` not in `"for"`, `"24/7"` requires the slash) / `find_matching_terms` order + dedupe
  - Capability detection: `"Stapler Circumcision"` → no `EMERGENCY_TRAUMA`; `"Find dialysis centers in Uttar Pradesh"` → `DIALYSIS_RENAL` only; real emergency text → `EMERGENCY_TRAUMA`; `"kidney stones"` → no `DIALYSIS_RENAL`
  - Taxonomy: `"kidney"` / `"renal"` not in `DIALYSIS_RENAL` keywords; every `EMERGENCY_TRAUMA` strong-evidence term is clinically specific
  - Evidence citation: stapler text → no emergency evidence; real emergency text → strong emergency evidence; `"haemodialysis machine"` → strong dialysis evidence; `"kidney stones"` → no dialysis evidence
  - Validator: emergency validation fails for generic surgery, passes for clinical phrasing; dialysis validation fails for a homeopathy clinic; `CR_HIGH_ACUITY_CLAIM_NO_EVIDENCE` fires on a claim-only emergency record
  - Local retriever ranking: a `"Haemodialysis Centre"` record outranks a `"Kidney Stone Specialist"` record on a dialysis query; name-match bonus actually applied
  - Recommendation engine: Tavily verified-but-no-capability path produces the new identity-only language in `reason_for_recommendation` and `human_next_steps`; verified-with-capability path lists the verified capability
  - End-to-end: `"Find dialysis centers in Uttar Pradesh"` against a small fixture returns a dialysis facility on top and **does not** carry `EMERGENCY_TRAUMA` in `interpreted_intent`
- [x] Smoke outputs regenerated under `data/outputs/stage16/`:
  - `maharashtra_emergency_local.{json,md}` — local-only run, top result is a genuine emergency / trauma facility
  - `up_dialysis_local.{json,md}` — local-only run, top result is a dialysis facility, no `EMERGENCY_TRAUMA` in interpreted intent
  - `up_dialysis_tavily.{json,md}` — Tavily-enabled (`--web-depth basic --max-web-verified 2`); when a verified result has empty `matched_capability`, the new identity-only wording surfaces in `reason_for_recommendation` and the corresponding `human_next_steps` step
- [x] All tests passing (440 → 463 tests; +23 new clinical-matching tests, no regressions)
- [x] **Stage 17 — Real Vector-Enabled Agent Smoke Test**
  - `requirements.txt` — added `databricks-vectorsearch>=0.40` (the package the main team validated against the live workspace; `databricks-sdk` was insufficient on this index)
  - `config/settings.py` — `vector_search_endpoint` / `vector_search_index` now resolve from three accepted env names each via `pydantic.AliasChoices`: `VECTOR_SEARCH_ENDPOINT` / `DATABRICKS_VECTOR_SEARCH_ENDPOINT` / **`DATABRICKS_VECTOR_ENDPOINT`** (new short alias) and `VECTOR_SEARCH_INDEX` / `DATABRICKS_VECTOR_INDEX_NAME` / **`DATABRICKS_VECTOR_INDEX`** (new short alias). Existing `VECTOR_SEARCH_ENABLED` / `ENABLE_VECTOR_SEARCH` pair unchanged.
  - `.env.example` — both short aliases documented with comments calling out the canonical name
  - `agent_core/vector_retriever.py` — rewritten end-to-end against `databricks.vector_search.client.VectorSearchClient`:
    - `DEFAULT_RETURN_COLUMNS` is exactly the eight Stage-17 columns (`facility_id`, `name`, `state`, `city`, `facility_type`, `trust_score`, `trust_category`, `recommendation_readiness`); `score`, `latitude`, `longitude` deliberately omitted — Databricks adds `score` to the manifest automatically and asking for it returns "column not found"
    - Lazy `_get_client()` constructs `VectorSearchClient(workspace_url=..., personal_access_token=..., disable_notice=True)` and caches it; `_get_index(client)` resolves the index handle via `client.get_index(endpoint_name=..., index_name=...)`
    - Filter contract: `filters={"state": "Bihar"}` (a Python dict). On `TypeError` (older SDK builds that don't accept the kwarg) or any "filter"-shaped exception message, retries the same query without filters and returns `available=true`, `filter_applied=false`, `reason="ok_without_filter"` — the agent stays useful and the local retriever still narrows by state
    - `filters_json` is **never** used as a primary argument. Reranker is **not** requested.
    - `_parse_response()` handles both dict-shape responses (live `databricks-vectorsearch`) and `SimpleNamespace`-shape responses (legacy `databricks-sdk` test fixtures) — extracts `facility_id`, maps Databricks `score` → `similarity_score`, places the other seven columns into `metadata`, tolerates missing/non-numeric scores (→ `0.0`)
    - **Never raises**: SDK import failure → `databricks_sdk_unavailable`; client construction → `query_failed: <ExceptionType>: …`; missing host/token/endpoint/index → stable reason codes
    - `VectorSearchResponse` gained `filter_applied: bool`, `endpoint: str`, `index: str` so callers can show what actually happened on the wire
  - `agent_core/recommendation_engine.py`:
    - New `_build_vector_filters(intent)` — pushes `{"state": intent.state}` into the vector call when state is present, returns `None` otherwise (matches the only filter shape the main team validated; every other narrowing happens locally so a filter mismatch can never silently drop hits)
    - Vector candidates are merged into local candidates by `facility_id`; vector-only hits are enriched from the local DataFrame, missing facility_ids are skipped with an audit note
    - 9-component score uses the existing `vector_similarity_component` (saturated and clamped); local evidence still wins over similarity — vector is retrieval support, not the final authority
    - `retrieval_summary` now carries `vector_filter_applied`, `vector_filters_requested`, `vector_endpoint`, `vector_index` in addition to the existing `vector_enabled` / `vector_available` / `vector_count` / `vector_reason` / `merged_count` / `local_count`
    - `trace_summary["vector"]` mirrors the same fields plus the result count
  - `run_agent_demo.py`:
    - Banner now reads Databricks config from `config.settings.settings` (so `.env` values loaded by `pydantic-settings` are visible — `os.environ` alone was misleading); token is reported as `present` / `MISSING / placeholder` only, never printed
    - Per-query console line includes `vector_enabled`, `vector_available`, `vector_count`, `vector_filter_applied`
    - Markdown report gains a dedicated `## Vector Search` section with enabled / available / count / reason / filter_applied / endpoint / index plus per-recommendation `vector_similarity_component` for the top results
  - `tests/test_vector_retriever.py` — rewritten for the new SDK contract (33 tests):
    - `score` not in requested columns; filters passed as a Python dict; `filters=None` path; filter-`TypeError` retry path returns `filter_applied=false` + `reason="ok_without_filter"`; non-TypeError filter-shaped errors also retried; `endpoint` / `index` echoed in success and unavailable responses; dict-shape and `SimpleNamespace`-shape parsing; missing host/token/endpoint/index/disabled paths; missing manifest, empty data_array, malformed rows, non-numeric / null score → `0.0`
    - All tests use `MagicMock` SDK + a fake index — never contacts Databricks
  - `tests/test_recommendation_engine.py` — added 6 Stage-17 tests:
    - `filters={"state": ...}` pushed when `intent.state` is present
    - `filters=None` pushed when `intent.state` is blank
    - `retrieval_summary` carries `vector_endpoint`, `vector_index`, `vector_filter_applied`, `vector_filters_requested`
    - `filter_applied=false` from the retriever propagates to `retrieval_summary`
    - Missing Databricks env with `enable_vector_search=True` does not crash — agent falls back to local retrieval
    - `vector_similarity_component > 0.0` for at least one candidate when the mocked retriever returns a score
  - `tests/test_run_agent_demo.py` — added 3 Stage-17 tests:
    - `--enable-vector` passes `enable_vector_search=True` into `run_recommendation`
    - No `--enable-vector` keeps vector disabled (no `VectorRetriever` constructed)
    - Markdown report contains the `## Vector Search` section with `enabled` / `available` / `count` / `reason` / `filter_applied` / `endpoint` / `index`
  - `docs/VECTOR_REAL_SMOKE_TEST.md` (new) — full Stage-17 runbook: Databricks setup values, `.env` variables, exact commands, per-query result tables, known SDK notes (no `score` in columns, dict filters, `filters_json` doesn't work, reranker disabled), troubleshooting matrix, and a mapping table of contract → code → test
  - **Real vector smoke runs (live Databricks workspace, Tavily off):**
    - **Bihar ICU** (`python run_agent_demo.py --query "Find trusted ICU hospitals in Bihar" --enable-vector --max-results 5 --output-json data/outputs/vector_smoke_bihar_icu.json --output-md data/outputs/vector_smoke_bihar_icu.md`):
      `vector_enabled=true`, `vector_available=true`, `vector_count=20`, `vector_reason=ok`, `filter_applied=true`, `local_count=164`, `merged_count=165`, `returned=5`. Top 5 are all in Bihar; Braham Jyoti Hospital scores `vector_similarity_component=0.0949 > 0`. **No fallback used.**
    - **UP dialysis** (`python run_agent_demo.py --query "Find dialysis centers in Uttar Pradesh" --enable-vector --max-results 5 --output-json data/outputs/vector_smoke_up_dialysis.json --output-md data/outputs/vector_smoke_up_dialysis.md`):
      `vector_enabled=true`, `vector_available=true`, `vector_count=20`, `vector_reason=ok`, `filter_applied=true`, `local_count=200`, `merged_count=214`, `returned=5`. Intent stayed `DIALYSIS_RENAL` (Stage 16 patch holds — no false `EMERGENCY_TRAUMA` from "centers"). Top 1 is `Dr. Mudit Khurana Dialysis Centre` with `vector_similarity_component=0.0991`; #4 also scored `0.0935`. **No fallback used.**
    - Output files generated: `data/outputs/vector_smoke_bihar_icu.{json,md}`, `data/outputs/vector_smoke_up_dialysis.{json,md}`
  - All tests passing (463 → **481 tests**; +18 new Stage-17 tests across vector_retriever, recommendation_engine, run_agent_demo). No backend changes, no frontend code, no secrets committed, zero Tavily credits spent during automated tests.
  - **Next step: Stage 18 — Combined Vector + Tavily Agent Test** (run a single query with both `--enable-vector` and `--enable-tavily`, verify recommendations carry vector similarity *and* web verification, document credit / fallback behaviour, and add Stage-18 regression tests).

---

## Not Yet Done

- [ ] `agent_core/intent_parser.py` — LLM upgrade path (currently keyword/regex; LLM layer deferred)
- [x] `agent_core/intent_parser.py` — fix substring over-extraction on short keywords (e.g. `"ER"` in `"centers"`, `"OR"` in `"support"`/`"for"`) by switching short tokens to word-boundary matching; **fixed in Stage 16** via `term_matches()` / `find_matching_terms()` in `capability_taxonomy.py` (which the parser calls through `find_capabilities_in_text()`)
- [ ] `agent_core/intent_parser.py` — broaden `trust_preference="verification_ok"` triggers to cover phrasings such as `"need human verification"`, `"requires verification"` (surfaced by GQ-009)
- [ ] `agent_core/vector_source_builder.py` — `build_vector_source()` file I/O wrapper (reads CSV/parquet, writes output)
- [ ] `agent_core/mlflow_tracing.py` — MLflow tracing implementation
- [ ] `notebooks/03_agent_batch_evaluation.py` — batch evaluation notebook
- [x] Load real 10,000-facility dataset into `data/raw/` (file present at `caregrid_backend_export_full.csv`, 10,000 rows × 35 columns, 34 unique states)
- [ ] Build vector source CSV/parquet in `data/vector_source/`
- [x] Create Databricks vector index (main team provisioned `workspace.default.caregrid_vector_index` against `caregrid-vector-endpoint`, 10,000 rows indexed, Delta Sync / Hybrid, `databricks-gte-large-en` on `vector_text` — Stage 17 verified end-to-end against the live index)
- [ ] Stage 18 — Combined Vector + Tavily Agent Test (single query exercising both `--enable-vector` and `--enable-tavily`)

---

## Prompt History

| # | Date | Prompt Summary | Stage |
| --- | --- | --- | --- |
| 1 | 2026-04-26 | Initial project scaffold — structure, config, placeholders, docs | Scaffold |
| 2 | 2026-04-26 | Settings, data contract, schemas — all env vars, constants, Pydantic models | Settings + Schemas |
| 3 | 2026-04-26 | Healthcare capability taxonomy — 13 capabilities, 4 helpers, 30 new tests | Taxonomy |
| 4 | 2026-04-26 | Natural-language intent parser — state/city/facility/trust/urgency/flags, 64 tests | Intent Parser |
| 5 | 2026-04-26 | Evidence builder + vector source preparation — _clean_value, build_combined_evidence, build_vector_text, prepare_vector_source_dataframe, 74 tests | Evidence + Vector Prep |
| 6 | 2026-04-26 | Databricks notebook 01 — 7-cell `prepare_vector_source` notebook (load → select → build vector_text → quality → save → verify) writing `workspace.default.caregrid_vector_source` | Notebook 01 |
| 7 | 2026-04-26 | Vector Search setup — rewritten `docs/VECTOR_DB_PLAN.md` with locked names + `notebooks/02_create_vector_index_notes.py` (endpoint + Delta Sync index + ready-check + smoke-test query, no secrets) | Vector Search Setup |
| 8 | 2026-04-26 | Vector retriever — `VectorRetriever`, `VectorSearchResult`, `VectorSearchResponse`; graceful unavailable on disabled / missing env / SDK error / query error; lazy `databricks-sdk` import; 24 tests, never touches real Databricks | Vector Retriever |
| 9 | 2026-04-26 | Local retriever fallback — `retrieve_local_candidates(df, intent, limit_pool)` with `LocalCandidate`; strict filter then cascading relaxation (trust → facility_type, never state unless opted-in); capability scoring across 6 text fields with strong-evidence weighting and capability bonus; 20 tests | Local Retriever |
| 10 | 2026-04-26 | Evidence snippet extraction — `extract_evidence_snippets(record, requested_capabilities)` with `EvidenceSnippet.support_level` (strong/moderate/weak/contradiction); 6-field priority scan, sentence/segment splitter, equipment/procedures preferred, max 3 per capability; 25 tests | Evidence Citation |
| 11 | 2026-04-26 | Validator / self-correction logic — `validate_candidate(record, requested_capabilities, evidence_snippets)` with 6 per-capability rule sets (ICU/Surgery/Dialysis/Oncology/Emergency/Neonatal), four-level severity, recommendation_impact values, and contradiction integration via rewritten `contradiction_rules.py` (5 rules using real `TRUST_CATEGORIES`/`RECOMMENDATION_READINESS_VALUES`); 27 validator tests | Validator |
| 12 | 2026-04-26 | Optional Tavily external verification — extended `WebVerificationResult` (12 new optional fields), in-memory TTL `TavilyCache` (24h, deterministic key, capability-order-insensitive), `verify_facility_web_presence(...)` and `verify_top_recommendations(...)` with `basic`/`advanced`/`demo` depth modes, name+location+capability scoring (verified/partial/unverified/skipped/error), graceful degradation on disabled / missing key / SDK / API errors (errors never cached), `docs/TAVILY_PLAN.md` (no secrets); 34 tests, no real Tavily SDK invoked | Tavily Verification |
| 13 | 2026-04-26 | Final recommendation engine — `run_recommendation()` orchestrator wires intent parser → local retriever → optional vector retriever → merge → evidence citation → validator → 9-component scoring → optional Tavily → `AgentResponse` with full `retrieval_summary` + `trace_summary` + audit log; new `ScoreBreakdown` model and Stage-13 fields on `AgentRecommendation` and `AgentResponse`; `AuditLogger` class (in-memory + optional JSONL) with module singleton; 30 new orchestrator tests plus the 3 preserved Stage-1 `recommend()` tests; 354 tests total | Recommendation Engine |
| 14 | 2026-04-26 | Golden query evaluation suite — 10 curated `GOLDEN_QUERIES` in `agent_core/demo_queries.py`; canonical 11-row in-memory fixture covering every query; parametrized universal-contract / intent-extraction / evidence-snippet tests + 10 per-query targeted tests + parametrized mocked-Tavily smoke test (60 new tests, all green); `docs/GOLDEN_QUERY_RESULTS.md` with the full evaluation table and a "known parser gaps" appendix; bug-fix in `tavily_verifier.py` so cache hits return the *caller's* `facility_id` (with a regression test); 407 tests total | Golden Queries |
| 15 | 2026-04-26 | Tavily live wiring + dual env-var name compatibility — `config/settings.py` now uses `pydantic.AliasChoices` so `TAVILY_ENABLED`/`ENABLE_TAVILY`, `TAVILY_MAX_WEB_VERIFIED`/`TAVILY_MAX_RESULTS`, `VECTOR_SEARCH_ENABLED`/`ENABLE_VECTOR_SEARCH`, and the two Databricks endpoint/index aliases all resolve to the same fields; `populate_by_name=True` keeps direct kwarg construction working in tests. `.env.example` rewritten to show both styles; local `.env` created (gitignored) with a real key; `test_settings_defaults` hardened to ignore the on-disk `.env`; 11 new alias tests; live smoke against `Apollo Hospitals, Mumbai` returned `verified` (score 0.7); 419 tests total | Tavily Live Wiring |
| 15c | 2026-04-26 | Real Dataset + Real Tavily Smoke Test Runner — `run_agent_demo.py` (CLI + 6 public functions, real-CSV loader, dataset validator, 5 default queries, JSON + Markdown writers, structured per-query Markdown sections); `tests/test_run_agent_demo.py` (21 tests, mock-based isolation guarantees no real Tavily/Databricks calls); `docs/TAVILY_REAL_SMOKE_TEST.md` (live smoke runbook with credit safety rules and 4 ways to confirm the call was real); `docs/REAL_INTEGRATION_RUNBOOK.md` (operator runbook for local / Tavily / vector runs); live default run against the real 10k CSV produced JSON + Markdown outputs end-to-end; 440 tests total | Real Dataset Runner |
| 16 | 2026-04-26 | Clinical Matching Quality Patch — safe matching helpers (`normalize_text`, `term_matches`, `find_matching_terms`) in `capability_taxonomy.py` with strict word-boundary rules for short / symbol-bearing tokens; `EMERGENCY_TRAUMA` strong evidence restricted to clinically meaningful phrases (no more `surgery` / `treatment` satisfying emergency); `DIALYSIS_RENAL` lost bare `kidney` / `renal` keywords (no more matches on `kidney stones` / `adrenal`); `evidence_citation.py`, `validator.py`, `local_retriever.py`, and (transitively) `intent_parser.py` rewired through the safe helpers; `WEIGHT_NAME_MATCH = 3.0` in `local_retriever.py` boosts capability-named facilities; new 9th score component `_W_LOCAL_RELEVANCE = 0.10` in `recommendation_engine.py` lets depth of local matches drive ranking (fixes Maharashtra emergency GQ-003); Tavily verified-but-no-capability path now produces explicit "identity/location only — clinical capability not confirmed online" wording in `reason_for_recommendation` + `human_next_steps`; new `CR_HIGH_ACUITY_CLAIM_NO_EVIDENCE` contradiction rule closes the GQ-010 sketchy-hospital loophole (claim of emergency / trauma / ICU / dialysis / critical care + empty `equipment` AND `procedures` → high-severity contradiction); `tests/test_clinical_matching_quality.py` adds 23 regression tests; smoke outputs regenerated under `data/outputs/stage16/`; 463 tests total | Clinical Matching Quality |
| 17 | 2026-04-26 | Real Vector-Enabled Agent Smoke Test — switched the retriever from `databricks-sdk` to `databricks-vectorsearch>=0.40` (the package the main team validated against the live workspace); `agent_core/vector_retriever.py` rewritten around `VectorSearchClient` + cached `get_index(...)` handle, requesting the eight Stage-17 columns only (no `score` — Databricks adds it automatically), passing `filters={"state": "..."}` as a Python dict, and transparently retrying without filters on `TypeError` (or any filter-shaped exception) with `reason="ok_without_filter"`; `VectorSearchResponse` gained `filter_applied` / `endpoint` / `index`; `_parse_response()` handles both dict-shape (live) and `SimpleNamespace`-shape (legacy) responses, mapping `score` → `similarity_score` with safe fallbacks; `agent_core/recommendation_engine.py` now builds `{"state": intent.state}` filters via `_build_vector_filters`, propagates `vector_filter_applied` / `vector_filters_requested` / `vector_endpoint` / `vector_index` into both `retrieval_summary` and `trace_summary["vector"]`, and keeps the existing `vector_similarity_component`; `config/settings.py` adds short aliases `DATABRICKS_VECTOR_ENDPOINT` / `DATABRICKS_VECTOR_INDEX` via `pydantic.AliasChoices`; `requirements.txt` adds `databricks-vectorsearch>=0.40`; `run_agent_demo.py` reads Databricks config from `Settings` (so `.env` is visible in the banner), adds vector status to the per-query console line, and emits a dedicated `## Vector Search` Markdown section; 33-test rewrite of `test_vector_retriever.py` plus 6 new Stage-17 recommendation engine tests + 3 new run-agent-demo tests, all mocked (zero real Databricks calls in CI, zero Tavily credits); `docs/VECTOR_REAL_SMOKE_TEST.md` (new) captures the live runbook and result tables. **Live smoke verified:** Bihar ICU (`vector_count=20`, `filter_applied=true`, top-2 has `vector_similarity_component=0.0949`) and UP dialysis (`vector_count=20`, `filter_applied=true`, top-1 `Dr. Mudit Khurana Dialysis Centre` with `vector_similarity_component=0.0991`, intent stayed `DIALYSIS_RENAL`); 481 tests total | Real Vector Smoke Test |
