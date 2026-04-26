# CareGrid Vector Agent — Test Results

> Snapshot of the most recent full pytest run. Regenerate at any time
> with the **Regeneration** command at the bottom of this file.

---

## Run metadata

| Field | Value |
| --- | --- |
| **Last run** | 2026-04-26 |
| **Total tests** | **440** |
| **Passed** | **440** |
| **Failed** | **0** |
| **Errors** | **0** |
| **Skipped** | **0** |
| **Warnings** | **0** |
| **Wall time** | 3.56 s |
| **Python** | 3.13.13 |
| **pytest** | 8.2.2 |
| **pluggy** | 1.6.0 |
| **plugins** | anyio-4.13.0, mock-3.15.1 |
| **Platform** | win32 |
| **Working dir** | `D:\caregrid_vector_agent` |

**Status: ALL TESTS PASS ✅**

---

## Summary by module

| # | Module | Tests | Passed | Failed | Coverage area |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | `test_capability_taxonomy.py` | 30 | 30 | 0 | 13 capabilities, completeness, helpers |
| 2 | `test_evidence_builder.py` | 74 | 74 | 0 | clean_value, build_combined_evidence, build_vector_text, prepare_vector_source_dataframe |
| 3 | `test_evidence_citation.py` | 25 | 25 | 0 | extract_evidence_snippets, support levels, field priority |
| 4 | `test_golden_queries.py` | 60 | 60 | 0 | 10 GQ contract + intent + evidence + per-query + mocked-Tavily + 5 DQ legacy |
| 5 | `test_intent_parser.py` | 64 | 64 | 0 | parse_query_intent, state/city/facility/trust/urgency/flags |
| 6 | `test_local_retriever.py` | 20 | 20 | 0 | retrieve_local_candidates, relaxation cascade, ranking |
| 7 | `test_recommendation_engine.py` | 33 | 33 | 0 | run_recommendation orchestrator + legacy recommend |
| 8 | `test_run_agent_demo.py` | 21 | 21 | 0 | CLI runner, validators, JSON/MD writers, network isolation |
| 9 | `test_settings.py` | 27 | 27 | 0 | Settings, env-var aliases, constants, schema instantiation |
| 10 | `test_tavily_verifier.py` | 35 | 35 | 0 | verify_facility_web_presence, verify_top_recommendations, cache |
| 11 | `test_validator.py` | 27 | 27 | 0 | validate_candidate, contradiction_rules |
| 12 | `test_vector_retriever.py` | 24 | 24 | 0 | VectorRetriever, graceful unavailable paths |
| | **Total** | **440** | **440** | **0** | |

---

## 1. `test_capability_taxonomy.py` — 30 / 30 passed

Verifies the 13 healthcare capabilities and their helper functions.

| # | Test | Status |
| --- | --- | --- |
| 1 | `test_all_required_capabilities_exist` | ✅ |
| 2 | `test_capability_count` | ✅ |
| 3 | `test_each_capability_has_required_fields` | ✅ |
| 4 | `test_capability_index_matches_list` | ✅ |
| 5 | `test_icu_has_ventilator_keyword` | ✅ |
| 6 | `test_icu_has_oxygen_term` | ✅ |
| 7 | `test_icu_is_high_acuity` | ✅ |
| 8 | `test_icu_detected_in_text` | ✅ |
| 9 | `test_dialysis_has_dialysis_machine_keyword` | ✅ |
| 10 | `test_dialysis_has_hemodialysis_keyword` | ✅ |
| 11 | `test_dialysis_is_high_acuity` | ✅ |
| 12 | `test_dialysis_detected_in_text` | ✅ |
| 13 | `test_oncology_has_cancer_keyword` | ✅ |
| 14 | `test_oncology_has_chemotherapy_keyword` | ✅ |
| 15 | `test_oncology_is_high_acuity` | ✅ |
| 16 | `test_oncology_detected_in_text` | ✅ |
| 17 | `test_neonatal_has_incubator_equipment` | ✅ |
| 18 | `test_neonatal_is_high_acuity` | ✅ |
| 19 | `test_neonatal_detected_in_text` | ✅ |
| 20 | `test_high_acuity_includes_icu` | ✅ |
| 21 | `test_high_acuity_includes_emergency` | ✅ |
| 22 | `test_high_acuity_includes_dialysis` | ✅ |
| 23 | `test_high_acuity_includes_oncology` | ✅ |
| 24 | `test_high_acuity_includes_neonatal` | ✅ |
| 25 | `test_high_acuity_count` | ✅ |
| 26 | `test_low_acuity_capabilities_excluded` | ✅ |
| 27 | `test_find_capabilities_empty_text` | ✅ |
| 28 | `test_find_capabilities_case_insensitive` | ✅ |
| 29 | `test_find_capabilities_no_duplicates` | ✅ |
| 30 | `test_get_capability_raises_for_unknown` | ✅ |

---

## 2. `test_evidence_builder.py` — 74 / 74 passed

Six test classes covering the value cleaner, evidence builders, and the vector source DataFrame preparation.

### 2.1 `TestCleanValue` (18 tests)

| Test | Status |
| --- | --- |
| `test_none_returns_empty` | ✅ |
| `test_float_nan_returns_empty` | ✅ |
| `test_math_nan_returns_empty` | ✅ |
| `test_string_nan_returns_empty` | ✅ |
| `test_string_nan_uppercase_returns_empty` | ✅ |
| `test_string_none_returns_empty` | ✅ |
| `test_string_null_returns_empty` | ✅ |
| `test_string_na_returns_empty` | ✅ |
| `test_empty_string_returns_empty` | ✅ |
| `test_whitespace_string_returns_empty` | ✅ |
| `test_list_like_with_quotes` | ✅ |
| `test_list_like_without_quotes` | ✅ |
| `test_list_like_double_quotes` | ✅ |
| `test_list_like_no_brackets_in_result` | ✅ |
| `test_normal_string_preserved` | ✅ |
| `test_strips_whitespace` | ✅ |
| `test_integer_value` | ✅ |
| `test_zero_is_not_empty` | ✅ |

### 2.2 `TestBuildCombinedEvidence` (18 tests)

| Test | Status |
| --- | --- |
| `test_contains_facility_name` | ✅ |
| `test_contains_facility_type` | ✅ |
| `test_contains_city` | ✅ |
| `test_contains_state` | ✅ |
| `test_contains_specialties` | ✅ |
| `test_contains_procedures` | ✅ |
| `test_contains_equipment` | ✅ |
| `test_contains_capabilities` | ✅ |
| `test_contains_evidence_summary` | ✅ |
| `test_contains_evidence_text` | ✅ |
| `test_returns_string` | ✅ |
| `test_empty_record_returns_empty_string` | ✅ |
| `test_minimal_record_contains_name` | ✅ |
| `test_none_fields_skipped` | ✅ |
| `test_nan_fields_skipped` | ✅ |
| `test_list_like_fields_cleaned` | ✅ |
| `test_city_state_combined_in_location` | ✅ |
| `test_city_only_no_extra_comma` | ✅ |

### 2.3 `TestBuildEvidence` (6 tests)

| Test | Status |
| --- | --- |
| `test_returns_snippet_list` | ✅ |
| `test_empty_string_returns_empty_list` | ✅ |
| `test_none_returns_empty_list` | ✅ |
| `test_nan_returns_empty_list` | ✅ |
| `test_long_text_truncated_at_500` | ✅ |
| `test_source_field_default` | ✅ |

### 2.4 `TestBuildEvidenceFromRecord` (4 tests)

| Test | Status |
| --- | --- |
| `test_full_record_returns_snippet` | ✅ |
| `test_empty_record_no_facility_id_returns_empty` | ✅ |
| `test_all_empty_fields_returns_empty` | ✅ |
| `test_snippet_contains_name` | ✅ |

### 2.5 `TestBuildVectorText` (11 tests)

| Test | Status |
| --- | --- |
| `test_contains_facility_name` | ✅ |
| `test_contains_city` | ✅ |
| `test_contains_state` | ✅ |
| `test_contains_specialties` | ✅ |
| `test_contains_equipment` | ✅ |
| `test_contains_evidence_text` | ✅ |
| `test_returns_string` | ✅ |
| `test_empty_record_returns_string` | ✅ |
| `test_minimal_record_contains_name` | ✅ |
| `test_no_list_brackets_in_output` | ✅ |
| `test_no_null_noise` | ✅ |

### 2.6 `TestPrepareVectorSourceDataframe` (17 tests)

| Test | Status |
| --- | --- |
| `test_output_columns_all_present` | ✅ |
| `test_output_columns_in_order` | ✅ |
| `test_no_missing_facility_id` | ✅ |
| `test_vector_text_column_populated` | ✅ |
| `test_vector_text_contains_facility_name` | ✅ |
| `test_vector_text_contains_evidence` | ✅ |
| `test_combined_medical_evidence_preserved_when_present` | ✅ |
| `test_combined_medical_evidence_built_when_absent` | ✅ |
| `test_missing_columns_filled_with_defaults` | ✅ |
| `test_existing_trust_score_preserved` | ✅ |
| `test_latitude_longitude_preserved` | ✅ |
| `test_handles_multiple_rows` | ✅ |
| `test_empty_dataframe_returns_empty_with_columns` | ✅ |
| `test_raises_without_facility_id_column` | ✅ |
| `test_raises_with_null_facility_id` | ✅ |
| `test_does_not_modify_input_dataframe` | ✅ |
| `test_nan_in_specialties_cleaned` | ✅ |

---

## 3. `test_evidence_citation.py` — 25 / 25 passed

| # | Test | Status |
| --- | --- | --- |
| 1 | `test_support_level_constants` | ✅ |
| 2 | `test_evidence_fields_priority_is_six_fields` | ✅ |
| 3 | `test_max_snippets_per_capability_is_three` | ✅ |
| 4 | `test_icu_with_ventilator_returns_strong_evidence` | ✅ |
| 5 | `test_dialysis_machine_returns_strong_evidence` | ✅ |
| 6 | `test_oncology_with_only_cancer_text_returns_moderate_or_weak` | ✅ |
| 7 | `test_no_evidence_returns_empty_list` | ✅ |
| 8 | `test_long_evidence_returns_concise_snippets` | ✅ |
| 9 | `test_max_three_snippets_per_capability` | ✅ |
| 10 | `test_strong_snippets_outrank_weak` | ✅ |
| 11 | `test_field_priority_breaks_ties_within_a_level` | ✅ |
| 12 | `test_dedup_by_excerpt_text` | ✅ |
| 13 | `test_multiple_capabilities_returns_per_capability_snippets` | ✅ |
| 14 | `test_unknown_capability_id_is_silently_skipped` | ✅ |
| 15 | `test_snippet_has_all_expected_fields` | ✅ |
| 16 | `test_relevance_score_matches_support_level` | ✅ |
| 17 | `test_empty_capability_list_returns_empty` | ✅ |
| 18 | `test_empty_record_returns_empty` | ✅ |
| 19 | `test_handles_nan_and_nullish_text_cells` | ✅ |
| 20 | `test_unwraps_list_like_strings` | ✅ |
| 21 | `test_segment_splitter_handles_pipes_and_newlines` | ✅ |
| 22 | `test_dental_alone_does_not_trigger_dentist_capability_logic` | ✅ |
| 23 | `test_format_citations_empty` (legacy) | ✅ |
| 24 | `test_format_citations_single_block` (legacy) | ✅ |
| 25 | `test_format_citations_multiple_blocks` (legacy) | ✅ |

---

## 4. `test_golden_queries.py` — 60 / 60 passed

10 curated `GOLDEN_QUERIES` (GQ-001…GQ-010) with parametrised contract / intent / evidence / mocked-Tavily tests, plus 10 per-query targeted tests, plus 5 legacy `DEMO_QUERIES`.

### 4.1 Universal contract (× 10)

| Test | Status |
| --- | --- |
| `test_golden_query_response_contract[GQ-001]` | ✅ |
| `test_golden_query_response_contract[GQ-002]` | ✅ |
| `test_golden_query_response_contract[GQ-003]` | ✅ |
| `test_golden_query_response_contract[GQ-004]` | ✅ |
| `test_golden_query_response_contract[GQ-005]` | ✅ |
| `test_golden_query_response_contract[GQ-006]` | ✅ |
| `test_golden_query_response_contract[GQ-007]` | ✅ |
| `test_golden_query_response_contract[GQ-008]` | ✅ |
| `test_golden_query_response_contract[GQ-009]` | ✅ |
| `test_golden_query_response_contract[GQ-010]` | ✅ |

### 4.2 Intent extraction (× 10)

| Test | Status |
| --- | --- |
| `test_golden_query_intent_extraction[GQ-001]` | ✅ |
| `test_golden_query_intent_extraction[GQ-002]` | ✅ |
| `test_golden_query_intent_extraction[GQ-003]` | ✅ |
| `test_golden_query_intent_extraction[GQ-004]` | ✅ |
| `test_golden_query_intent_extraction[GQ-005]` | ✅ |
| `test_golden_query_intent_extraction[GQ-006]` | ✅ |
| `test_golden_query_intent_extraction[GQ-007]` | ✅ |
| `test_golden_query_intent_extraction[GQ-008]` | ✅ |
| `test_golden_query_intent_extraction[GQ-009]` | ✅ |
| `test_golden_query_intent_extraction[GQ-010]` | ✅ |

### 4.3 Evidence snippets present (× 10)

| Test | Status |
| --- | --- |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-001]` | ✅ |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-002]` | ✅ |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-003]` | ✅ |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-004]` | ✅ |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-005]` | ✅ |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-006]` | ✅ |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-007]` | ✅ |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-008]` | ✅ |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-009]` | ✅ |
| `test_golden_query_evidence_snippets_present_when_recommendations_exist[GQ-010]` | ✅ |

### 4.4 Per-query targeted (× 10)

| Test | Status |
| --- | --- |
| `test_gq001_trusted_icu_returns_high_trust_first` | ✅ |
| `test_gq002_bihar_icu_returns_only_bihar_hospitals` | ✅ |
| `test_gq003_emergency_maharashtra_top_is_trauma_centre` | ✅ |
| `test_gq004_dialysis_uttar_pradesh` | ✅ |
| `test_gq005_oncology_gujarat` | ✅ |
| `test_gq006_maternity_tamil_nadu` | ✅ |
| `test_gq007_neonatal_icu_gujarat` | ✅ |
| `test_gq008_diagnostics_delhi` | ✅ |
| `test_gq009_dialysis_verification_includes_non_ready` | ✅ |
| `test_gq010_unsupported_emergency_claim_flagged` | ✅ |

### 4.5 Mocked Tavily smoke (× 10)

| Test | Status |
| --- | --- |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-001]` | ✅ |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-002]` | ✅ |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-003]` | ✅ |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-004]` | ✅ |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-005]` | ✅ |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-006]` | ✅ |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-007]` | ✅ |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-008]` | ✅ |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-009]` | ✅ |
| `test_golden_query_with_mocked_tavily_does_not_crash[GQ-010]` | ✅ |

### 4.6 Aggregate sanity (3 tests)

| Test | Status |
| --- | --- |
| `test_golden_queries_count_is_ten` | ✅ |
| `test_golden_queries_have_required_fields` | ✅ |
| `test_golden_queries_ids_are_unique` | ✅ |

### 4.7 Legacy `DEMO_QUERIES` (7 tests)

| Test | Status |
| --- | --- |
| `test_demo_queries_exist` | ✅ |
| `test_demo_queries_have_required_fields` | ✅ |
| `test_intent_parser_on_demo_queries[DQ-001]` | ✅ |
| `test_intent_parser_on_demo_queries[DQ-002]` | ✅ |
| `test_intent_parser_on_demo_queries[DQ-003]` | ✅ |
| `test_intent_parser_on_demo_queries[DQ-004]` | ✅ |
| `test_intent_parser_on_demo_queries[DQ-005]` | ✅ |

---

## 5. `test_intent_parser.py` — 64 / 64 passed

### 5.1 Backward-compat `parse_intent()` (8 tests)

| Test | Status |
| --- | --- |
| `test_parse_intent_returns_agent_intent` | ✅ |
| `test_parse_intent_detects_icu` | ✅ |
| `test_parse_intent_detects_dialysis` | ✅ |
| `test_parse_intent_detects_emergency` | ✅ |
| `test_parse_intent_detects_neonatal` | ✅ |
| `test_parse_intent_detects_oncology` | ✅ |
| `test_parse_intent_multiple_capabilities` | ✅ |
| `test_parse_intent_empty_query` | ✅ |

### 5.2 `parse_query_intent()` core (4 tests)

| Test | Status |
| --- | --- |
| `test_parse_query_intent_returns_agent_intent` | ✅ |
| `test_original_query_preserved` | ✅ |
| `test_normalized_query_lowercase_stripped` | ✅ |
| `test_normalized_query_collapses_whitespace` | ✅ |

### 5.3 State detection (7 tests, parametrised × 6 + 1)

| Test | Status |
| --- | --- |
| `test_state_detection[trusted ICU hospitals in Bihar-Bihar]` | ✅ |
| `test_state_detection[emergency hospitals in Maharashtra-Maharashtra]` | ✅ |
| `test_state_detection[dialysis centers in Uttar Pradesh-Uttar Pradesh]` | ✅ |
| `test_state_detection[oncology care in Gujarat-Gujarat]` | ✅ |
| `test_state_detection[maternity hospital in Tamil Nadu-Tamil Nadu]` | ✅ |
| `test_state_detection[diagnostics centers in Delhi-Delhi]` | ✅ |
| `test_state_none_when_absent` | ✅ |

### 5.4 City detection (5 tests)

| Test | Status |
| --- | --- |
| `test_city_detected_mumbai` | ✅ |
| `test_city_detected_bangalore` | ✅ |
| `test_city_none_when_only_state` | ✅ |
| `test_location_prefers_city_over_state` | ✅ |
| `test_location_falls_back_to_state` | ✅ |

### 5.5 Trust preference (5 tests)

| Test | Status |
| --- | --- |
| `test_trust_preferred_trusted_keyword` | ✅ |
| `test_trust_high_trust_phrase` | ✅ |
| `test_trust_reliable` | ✅ |
| `test_trust_verification_ok` | ✅ |
| `test_trust_unspecified` | ✅ |

### 5.6 Urgency (5 tests)

| Test | Status |
| --- | --- |
| `test_urgency_emergency` | ✅ |
| `test_urgency_urgent_keyword` | ✅ |
| `test_urgency_routine` | ✅ |
| `test_urgency_unspecified` | ✅ |
| `test_urgency_emergency_also_detects_capability` | ✅ |

### 5.7 Facility type (9 tests)

| Test | Status |
| --- | --- |
| `test_facility_type_hospital_singular` | ✅ |
| `test_facility_type_hospital_plural` | ✅ |
| `test_facility_type_clinic` | ✅ |
| `test_facility_type_doctor` | ✅ |
| `test_facility_type_pharmacy` | ✅ |
| `test_facility_type_dentist_keyword` | ✅ |
| `test_facility_type_dental_alone_is_not_dentist` | ✅ |
| `test_facility_type_dental_clinic_is_clinic` | ✅ |
| `test_facility_type_none_for_centers` | ✅ |

### 5.8 Capability detection (parametrised × 6)

| Test | Status |
| --- | --- |
| `test_capability_detected[trusted ICU hospitals in Bihar-ICU_CRITICAL_CARE]` | ✅ |
| `test_capability_detected[emergency hospitals in Maharashtra-EMERGENCY_TRAUMA]` | ✅ |
| `test_capability_detected[dialysis centers in Uttar Pradesh-DIALYSIS_RENAL]` | ✅ |
| `test_capability_detected[oncology care in Gujarat-ONCOLOGY]` | ✅ |
| `test_capability_detected[maternity hospital in Tamil Nadu-MATERNAL_CARE]` | ✅ |
| `test_capability_detected[diagnostics centers in Delhi-DIAGNOSTICS]` | ✅ |

### 5.9 Modifier flags + edge cases (14 tests)

| Test | Status |
| --- | --- |
| `test_proximity_near_me` | ✅ |
| `test_proximity_nearest` | ✅ |
| `test_proximity_not_requested` | ✅ |
| `test_web_verification_requested` | ✅ |
| `test_web_verification_not_requested` | ✅ |
| `test_vector_search_requested` | ✅ |
| `test_vector_search_not_requested` | ✅ |
| `test_min_trust_score_extracted` | ✅ |
| `test_min_trust_score_none_when_absent` | ✅ |
| `test_known_states_restricts_detection` | ✅ |
| `test_known_states_detects_when_present` | ✅ |
| `test_known_facility_types_restricts_detection` | ✅ |
| `test_known_facility_types_detects_when_present` | ✅ |
| `test_empty_query_all_defaults` | ✅ |
| `test_whitespace_only_query` | ✅ |

---

## 6. `test_local_retriever.py` — 20 / 20 passed

| # | Test | Status |
| --- | --- | --- |
| 1 | `test_local_candidate_defaults` | ✅ |
| 2 | `test_search_fields_constant_is_six_fields` | ✅ |
| 3 | `test_icu_query_returns_candidates` | ✅ |
| 4 | `test_dialysis_query_returns_candidates` | ✅ |
| 5 | `test_maharashtra_hospital_query_returns_only_hospitals` | ✅ |
| 6 | `test_fallback_records_relaxation_notes_for_trust_score` | ✅ |
| 7 | `test_fallback_records_relaxation_notes_for_facility_type` | ✅ |
| 8 | `test_fallback_records_both_relaxations_when_needed` | ✅ |
| 9 | `test_state_filter_is_not_relaxed_by_default` | ✅ |
| 10 | `test_state_filter_is_relaxed_when_explicitly_allowed` | ✅ |
| 11 | `test_ranking_is_score_then_trust_score_descending` | ✅ |
| 12 | `test_limit_pool_is_respected` | ✅ |
| 13 | `test_empty_dataframe_returns_empty_list` | ✅ |
| 14 | `test_handles_missing_optional_columns` | ✅ |
| 15 | `test_handles_nan_and_nullish_text_cells` | ✅ |
| 16 | `test_no_capabilities_falls_back_to_query_tokens` | ✅ |
| 17 | `test_relaxation_notes_are_per_candidate_not_shared` | ✅ |
| 18 | `test_legacy_retrieve_local_matches_keyword` | ✅ |
| 19 | `test_legacy_retrieve_local_no_match_returns_empty` | ✅ |
| 20 | `test_legacy_retrieve_local_top_k` | ✅ |

---

## 7. `test_recommendation_engine.py` — 33 / 33 passed

| # | Test | Status |
| --- | --- | --- |
| 1 | `test_trusted_icu_query_returns_structured_response` | ✅ |
| 2 | `test_response_contract_fields_are_present` | ✅ |
| 3 | `test_recommendation_contract_fields_are_present` | ✅ |
| 4 | `test_safety_note_always_present` | ✅ |
| 5 | `test_score_breakdown_components_are_set` | ✅ |
| 6 | `test_validation_findings_lower_score` | ✅ |
| 7 | `test_dialysis_query_returns_results_or_fallback` | ✅ |
| 8 | `test_no_match_returns_fallback_message` | ✅ |
| 9 | `test_max_results_truncates_recommendations` | ✅ |
| 10 | `test_min_trust_score_override_is_applied` | ✅ |
| 11 | `test_facility_type_override_is_applied` | ✅ |
| 12 | `test_tavily_disabled_path_returns_no_web_verification` | ✅ |
| 13 | `test_tavily_mocked_enabled_path_attaches_web_verification` | ✅ |
| 14 | `test_tavily_max_web_verified_respected` | ✅ |
| 15 | `test_tavily_zero_max_web_verified_skips_all` | ✅ |
| 16 | `test_vector_disabled_path_skips_vector_stage` | ✅ |
| 17 | `test_vector_mocked_path_boosts_local_candidate` | ✅ |
| 18 | `test_vector_unavailable_path_falls_back_silently` | ✅ |
| 19 | `test_vector_retriever_exception_is_swallowed` | ✅ |
| 20 | `test_vector_only_candidate_gets_added_via_lookup` | ✅ |
| 21 | `test_audit_logger_receives_pipeline_events` | ✅ |
| 22 | `test_default_audit_logger_when_none_passed` | ✅ |
| 23 | `test_empty_dataframe_does_not_crash` | ✅ |
| 24 | `test_blank_query_does_not_crash` | ✅ |
| 25 | `test_intent_parser_failure_is_swallowed` | ✅ |
| 26 | `test_local_retriever_failure_is_swallowed` | ✅ |
| 27 | `test_evidence_extractor_failure_is_swallowed` | ✅ |
| 28 | `test_reasoning_mentions_top_result` | ✅ |
| 29 | `test_human_next_steps_non_empty_for_every_recommendation` | ✅ |
| 30 | `test_emergency_query_adds_emergency_step` | ✅ |
| 31 | `test_recommend_filters_by_trust_score` (legacy) | ✅ |
| 32 | `test_recommend_sorted_descending` (legacy) | ✅ |
| 33 | `test_recommend_top_k` (legacy) | ✅ |

---

## 8. `test_run_agent_demo.py` — 21 / 21 passed (NEW)

| # | Test | Status |
| --- | --- | --- |
| 1 | `test_imports_cleanly` | ✅ |
| 2 | `test_required_columns_constant_complete` | ✅ |
| 3 | `test_get_default_demo_queries_returns_five` | ✅ |
| 4 | `test_get_default_demo_queries_exact_contents` | ✅ |
| 5 | `test_get_default_demo_queries_returns_fresh_copy` | ✅ |
| 6 | `test_validate_real_dataset_passes_with_full_columns` | ✅ |
| 7 | `test_validate_real_dataset_catches_missing_columns` | ✅ |
| 8 | `test_validate_real_dataset_handles_none` | ✅ |
| 9 | `test_load_real_dataset_missing_file_exits_cleanly` | ✅ |
| 10 | `test_load_real_dataset_reads_a_temp_csv` | ✅ |
| 11 | `test_save_json_output_writes_file` | ✅ |
| 12 | `test_save_json_output_creates_parent_dir` | ✅ |
| 13 | `test_save_markdown_report_writes_file` | ✅ |
| 14 | `test_save_markdown_report_includes_query_text` | ✅ |
| 15 | `test_save_markdown_report_handles_empty_results` | ✅ |
| 16 | `test_run_demo_queries_default_does_not_call_tavily` | ✅ |
| 17 | `test_run_demo_queries_default_does_not_call_databricks` | ✅ |
| 18 | `test_run_demo_queries_returns_agent_response_objects` | ✅ |
| 19 | `test_run_demo_queries_unknown_depth_falls_back_to_basic` | ✅ |
| 20 | `test_cli_help_runs_and_exits_zero` | ✅ |
| 21 | `test_cli_main_default_run` | ✅ |

---

## 9. `test_settings.py` — 27 / 27 passed

### 9.1 Settings instantiation + defaults (3 tests)

| Test | Status |
| --- | --- |
| `test_settings_instantiates` | ✅ |
| `test_settings_defaults` | ✅ |
| `test_settings_required_fields_exist` | ✅ |

### 9.2 Dual env-var name aliases (11 tests)

| Test | Status |
| --- | --- |
| `test_tavily_enabled_canonical_name` | ✅ |
| `test_tavily_enabled_alias_name` | ✅ |
| `test_tavily_max_web_verified_canonical_name` | ✅ |
| `test_tavily_max_web_verified_alias_name` | ✅ |
| `test_vector_search_enabled_canonical_name` | ✅ |
| `test_vector_search_enabled_alias_name` | ✅ |
| `test_vector_search_endpoint_canonical_name` | ✅ |
| `test_vector_search_endpoint_alias_name` | ✅ |
| `test_vector_search_index_canonical_name` | ✅ |
| `test_vector_search_index_alias_name` | ✅ |
| `test_tavily_api_key_loads_from_env` | ✅ |

### 9.3 Domain constants (4 tests)

| Test | Status |
| --- | --- |
| `test_trust_categories_exact` | ✅ |
| `test_trust_categories_length` | ✅ |
| `test_recommendation_readiness_exact` | ✅ |
| `test_recommendation_readiness_length` | ✅ |

### 9.4 Schema instantiation (9 tests)

| Test | Status |
| --- | --- |
| `test_facility_record_instantiates` | ✅ |
| `test_agent_query_instantiates` | ✅ |
| `test_agent_intent_instantiates` | ✅ |
| `test_evidence_snippet_instantiates` | ✅ |
| `test_validation_finding_instantiates` | ✅ |
| `test_web_verification_result_instantiates` | ✅ |
| `test_agent_recommendation_instantiates` | ✅ |
| `test_agent_response_instantiates` | ✅ |
| `test_agent_response_full` | ✅ |

---

## 10. `test_tavily_verifier.py` — 35 / 35 passed

| # | Test | Status |
| --- | --- | --- |
| 1 | `test_disabled_returns_skipped_and_does_not_call_factory` | ✅ |
| 2 | `test_missing_api_key_returns_skipped_and_does_not_call_factory` | ✅ |
| 3 | `test_missing_api_key_does_not_crash_with_default_settings` | ✅ |
| 4 | `test_unknown_depth_falls_back_to_basic` | ✅ |
| 5 | `test_mocked_successful_search_maps_to_verified` | ✅ |
| 6 | `test_no_results_returns_unverified_but_web_available` | ✅ |
| 7 | `test_results_without_match_returns_unverified` | ✅ |
| 8 | `test_partial_match_only_name_returns_partial` | ✅ |
| 9 | `test_cache_prevents_duplicate_call` | ✅ |
| 10 | `test_cache_hit_overrides_facility_id_with_caller_value` | ✅ |
| 11 | `test_cache_key_distinguishes_depth` | ✅ |
| 12 | `test_cache_key_distinguishes_capabilities` | ✅ |
| 13 | `test_cache_capabilities_order_does_not_matter` | ✅ |
| 14 | `test_cache_ttl_expires_entry` | ✅ |
| 15 | `test_cache_make_key_is_deterministic_and_normalised` | ✅ |
| 16 | `test_basic_depth_makes_one_call_and_uses_basic_search_depth` | ✅ |
| 17 | `test_advanced_depth_makes_two_calls_when_capabilities_given` | ✅ |
| 18 | `test_advanced_depth_collapses_to_one_call_without_capabilities` | ✅ |
| 19 | `test_demo_depth_extracts_official_looking_url` | ✅ |
| 20 | `test_client_factory_raises_import_error_returns_sdk_unavailable` | ✅ |
| 21 | `test_client_factory_raises_other_exception_returns_error` | ✅ |
| 22 | `test_search_call_raises_returns_error_with_short_message` | ✅ |
| 23 | `test_search_returns_garbage_does_not_crash` | ✅ |
| 24 | `test_error_results_are_not_cached` | ✅ |
| 25 | `test_verify_top_recommendations_respects_max_to_verify` | ✅ |
| 26 | `test_verify_top_recommendations_respects_depth` | ✅ |
| 27 | `test_verify_top_recommendations_works_with_dicts` | ✅ |
| 28 | `test_verify_top_recommendations_empty_input_returns_empty` | ✅ |
| 29 | `test_verify_top_recommendations_zero_limit_returns_empty` | ✅ |
| 30 | `test_verify_top_recommendations_disabled_returns_skipped_for_each` | ✅ |
| 31 | `test_verify_top_recommendations_per_item_overrides` | ✅ |
| 32 | `test_web_verification_result_default_values_safe` | ✅ |
| 33 | `test_returned_result_has_all_new_fields_populated` | ✅ |
| 34 | `test_verification_status_is_one_of_allowed_values` | ✅ |
| 35 | `test_verify_facility_legacy_shim_returns_skipped_when_no_key` | ✅ |

---

## 11. `test_validator.py` — 27 / 27 passed

### 11.1 Validator core (16 tests)

| Test | Status |
| --- | --- |
| `test_icu_claim_without_equipment_triggers_high_severity` | ✅ |
| `test_surgery_without_ot_or_anesthesia_triggers_finding` | ✅ |
| `test_dialysis_with_machine_passes_support` | ✅ |
| `test_emergency_with_ambulance_and_24x7_passes_support` | ✅ |
| `test_oncology_with_only_weak_text_returns_medium_severity` | ✅ |
| `test_terms_present_but_no_snippets_yields_weak_finding` | ✅ |
| `test_empty_requested_capabilities_returns_empty` | ✅ |
| `test_unknown_capability_is_silently_skipped` | ✅ |
| `test_empty_record_returns_empty_findings` | ✅ |
| `test_neonatal_with_incubator_passes` | ✅ |
| `test_multiple_capabilities_produce_one_finding_each` | ✅ |
| `test_duplicate_requested_capabilities_are_deduped` | ✅ |
| `test_short_token_ot_word_boundary_matching` | ✅ |
| `test_validation_finding_has_all_fields` | ✅ |
| `test_validation_rules_cover_six_required_capabilities` | ✅ |
| `test_strong_snippet_outranks_weak_snippet` | ✅ |

### 11.2 Contradiction rules (8 tests)

| Test | Status |
| --- | --- |
| `test_nan_and_null_record_fields_are_tolerated` | ✅ |
| `test_high_score_low_trust_category_is_contradiction` | ✅ |
| `test_ready_but_low_score_is_contradiction` | ✅ |
| `test_contradictions_appear_after_capability_findings` | ✅ |
| `test_no_contradiction_for_clean_record` | ✅ |
| `test_check_contradictions_returns_string_ids` | ✅ |
| `test_find_contradictions_returns_dicts_with_severity` | ✅ |
| `test_get_rule_returns_rule_or_none` | ✅ |

### 11.3 Edge case + legacy (3 tests)

| Test | Status |
| --- | --- |
| `test_contradictions_safe_on_empty_record` | ✅ |
| `test_validate_empty_response_has_warnings` (legacy) | ✅ |
| `test_validate_complete_response_no_warnings` (legacy) | ✅ |

---

## 12. `test_vector_retriever.py` — 24 / 24 passed

| # | Test | Status |
| --- | --- | --- |
| 1 | `test_vector_search_result_defaults` | ✅ |
| 2 | `test_vector_search_response_defaults` | ✅ |
| 3 | `test_is_available_when_disabled` | ✅ |
| 4 | `test_is_available_when_fully_configured` | ✅ |
| 5 | `test_is_available_when_field_missing[host-missing_databricks_host]` | ✅ |
| 6 | `test_is_available_when_field_missing[token-missing_databricks_token]` | ✅ |
| 7 | `test_is_available_when_field_missing[endpoint-missing_vector_search_endpoint]` | ✅ |
| 8 | `test_is_available_when_field_missing[index-missing_vector_search_index]` | ✅ |
| 9 | `test_search_disabled_returns_unavailable_gracefully` | ✅ |
| 10 | `test_search_disabled_does_not_call_databricks` | ✅ |
| 11 | `test_search_success_with_mocked_response` | ✅ |
| 12 | `test_search_passes_correct_kwargs_to_sdk` | ✅ |
| 13 | `test_search_with_filters_passes_json` | ✅ |
| 14 | `test_search_default_num_results_is_20` | ✅ |
| 15 | `test_search_returns_unavailable_when_sdk_raises` | ✅ |
| 16 | `test_search_returns_unavailable_when_client_construction_fails` | ✅ |
| 17 | `test_search_returns_unavailable_when_sdk_not_installed` | ✅ |
| 18 | `test_search_does_not_propagate_arbitrary_exceptions` | ✅ |
| 19 | `test_parse_response_handles_empty_data_array` | ✅ |
| 20 | `test_parse_response_handles_missing_manifest` | ✅ |
| 21 | `test_parse_response_handles_non_numeric_score` | ✅ |
| 22 | `test_parse_response_handles_null_score` | ✅ |
| 23 | `test_parse_response_skips_malformed_rows` | ✅ |
| 24 | `test_is_available_does_not_create_client` | ✅ |

---

## Coverage map (which area is exercised by which module)

| Functional area | Test modules |
| --- | --- |
| **Configuration** (env vars, aliases, domain constants) | `test_settings.py` |
| **Pydantic schemas** | `test_settings.py` (instantiation), every other module via real types |
| **Capability taxonomy** (13 capabilities) | `test_capability_taxonomy.py` |
| **Intent parsing** (NL → AgentIntent) | `test_intent_parser.py` |
| **Evidence builder** (clean, combine) | `test_evidence_builder.py` |
| **Vector source DataFrame prep** | `test_evidence_builder.py::TestPrepareVectorSourceDataframe` |
| **Evidence citation** (snippet extraction + support levels) | `test_evidence_citation.py` |
| **Validator + contradiction rules** | `test_validator.py` |
| **Local retriever** (pandas fallback) | `test_local_retriever.py` |
| **Vector retriever** (Databricks Mosaic AI) | `test_vector_retriever.py` |
| **Tavily verifier** (web verification + cache) | `test_tavily_verifier.py` |
| **Recommendation engine** (orchestrator) | `test_recommendation_engine.py` |
| **Golden query suite** (end-to-end on canonical fixture) | `test_golden_queries.py` |
| **Demo runner / CLI** (run_agent_demo.py) | `test_run_agent_demo.py` |

---

## Network isolation guarantees

The full test suite **never** contacts a real Tavily endpoint or a real
Databricks workspace. This is enforced explicitly in:

- `test_run_agent_demo.py::test_run_demo_queries_default_does_not_call_tavily`
  — patches `agent_core.tavily_verifier._default_client_factory` and
  asserts it is **not** called.
- `test_run_agent_demo.py::test_run_demo_queries_default_does_not_call_databricks`
  — patches `agent_core.recommendation_engine._build_default_vector_retriever`
  with `side_effect=AssertionError` so any unexpected call raises loudly.
- `test_tavily_verifier.py` — every test uses a `MagicMock` client
  factory; the real `tavily-python` SDK is never imported.
- `test_vector_retriever.py` — every test uses a mocked Databricks SDK;
  no workspace credentials are consulted.

---

## How tests are run

From the project root (`d:\caregrid_vector_agent`):

```bash
# Full suite, condensed output
python -m pytest

# Verbose output (every test name)
python -m pytest -v

# Single module
python -m pytest tests/test_run_agent_demo.py -v

# Re-run only the tests that failed last time
python -m pytest --lf
```

---

## Regenerating this document

When the test suite changes, regenerate the snapshot:

```bash
python -m pytest -v --tb=no > .pytest_v_output.txt 2>&1
```

Then update the **Run metadata** block at the top of this file with
the new totals and timestamp, and update each module's tables with any
added/removed/renamed tests. The pass/fail column comes from the
`PASSED` / `FAILED` markers in the verbose output.

A simple script could automate this — see
`scripts/refresh_test_results.py` (not yet created).

---

## Test-count history

| Stage | Date | Total tests | Δ | Notes |
| --- | --- | ---: | ---: | --- |
| Stage 1 — Scaffold | 2026-04-26 | 25 | +25 | Initial passable stubs |
| Stage 2 — Settings + Schemas | 2026-04-26 | 39 | +14 | `test_settings.py` instantiation tests |
| Stage 3 — Capability Taxonomy | 2026-04-26 | 74 | +35 | `test_capability_taxonomy.py` (30) + 5 demo |
| Stage 4 — Intent Parser | 2026-04-26 | 130 | +56 | `test_intent_parser.py` parametrised expansion |
| Stage 5 — Evidence Builder | 2026-04-26 | 204 | +74 | `test_evidence_builder.py` (74) |
| Stage 6 — Notebook 01 | 2026-04-26 | 204 | +0 | Notebook (not unit-tested) |
| Stage 7 — Vector DB Plan + Notebook 02 | 2026-04-26 | 204 | +0 | Docs + notebook |
| Stage 8 — Vector Retriever | 2026-04-26 | 227 | +23 | `test_vector_retriever.py` rewritten + expanded |
| Stage 9 — Local Retriever | 2026-04-26 | 244 | +17 | `test_local_retriever.py` expanded |
| Stage 10 — Evidence Citation | 2026-04-26 | 266 | +22 | `test_evidence_citation.py` expanded |
| Stage 11 — Validator | 2026-04-26 | 291 | +25 | `test_validator.py` expanded |
| Stage 12 — Tavily Verifier | 2026-04-26 | 324 | +33 | `test_tavily_verifier.py` rewritten |
| Stage 13 — Recommendation Engine | 2026-04-26 | 354 | +30 | `test_recommendation_engine.py` orchestrator tests |
| Stage 14 — Golden Queries | 2026-04-26 | 407 | +53 | `test_golden_queries.py` (60) – 7 (legacy moved) |
| Stage 15 — Tavily Live Wiring | 2026-04-26 | 419 | +12 | 11 alias tests + 1 isolation fix |
| Stage 15c — Demo Runner | 2026-04-26 | **440** | **+21** | `test_run_agent_demo.py` (current) |
