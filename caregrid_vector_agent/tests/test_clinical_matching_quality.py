"""
tests.test_clinical_matching_quality — Stage 16 regression suite.

These tests pin down the bug fixes shipped in the "Clinical Matching
Quality Patch": false EMERGENCY_TRAUMA detection on records like
``"Stapler Circumcision"`` / ``"Cataract surgery"``, false
EMERGENCY_TRAUMA detection from short-token leakage in queries like
``"Find dialysis centers in Uttar Pradesh"`` (where ``"centers"``
contains the substring ``"er"``), and the wrong dialysis ranking where
homoeopathy / kidney-stones-only clinics outranked real haemodialysis
facilities.

Every test in this file maps to a specific bug class so a regression in
the matching logic is loud and obvious.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from agent_core import recommendation_engine as engine
from agent_core.capability_taxonomy import (
    CAPABILITY_INDEX,
    find_capabilities_in_text,
    find_matching_terms,
    normalize_text,
    term_matches,
)
from agent_core.evidence_citation import extract_evidence_snippets
from agent_core.intent_parser import parse_query_intent
from agent_core.local_retriever import retrieve_local_candidates
from agent_core.schemas import WebVerificationResult
from agent_core.validator import validate_candidate


# ---------------------------------------------------------------------------
# Test fixtures — small in-memory facility records
# ---------------------------------------------------------------------------

def _facility(
    *,
    facility_id: str,
    name: str,
    state: str = "Uttar Pradesh",
    facility_type: str = "hospital",
    trust_score: float = 0.7,
    trust_category: str = "Reasonable",
    readiness: str = "Usable with verification",
    specialties: str = "",
    procedures: str = "",
    equipment: str = "",
    capabilities_raw: str = "",
    evidence_summary: str = "",
    combined: str = "",
) -> dict:
    return {
        "facility_id": facility_id,
        "name": name,
        "state": state,
        "facility_type": facility_type,
        "trust_score": trust_score,
        "trust_category": trust_category,
        "recommendation_readiness": readiness,
        "specialties": specialties,
        "procedures": procedures,
        "equipment": equipment,
        "capabilities_raw": capabilities_raw,
        "evidence_summary": evidence_summary,
        "combined_medical_evidence": combined,
    }


# ---------------------------------------------------------------------------
# 1. Safe matching helpers
# ---------------------------------------------------------------------------

class TestSafeMatchingHelpers:
    """normalize_text / term_matches / find_matching_terms."""

    def test_normalize_text_lowercases_and_strips(self):
        assert normalize_text("  Hello   WORLD  ") == "hello world"
        assert normalize_text(None) == ""
        assert normalize_text("") == ""

    def test_term_matches_word_boundary_short_tokens(self):
        # "ER" must NOT match inside longer words
        assert term_matches("Stapler Circumcision", "ER") is False
        assert term_matches("Cataract surgery", "ER") is False
        assert term_matches("dialysis centers", "ER") is False
        assert term_matches("Refractive Surgery", "ER") is False
        # "ER" MUST still match standalone or in proper phrases
        assert term_matches("ER department open 24/7", "ER") is True
        assert term_matches("Casualty; ER triage on site", "ER") is True
        assert term_matches("Visit our ER", "ER") is True

    def test_term_matches_other_short_tokens_word_bounded(self):
        # OT, OR, A&E, ICU all need boundaries
        assert term_matches("rotor blade", "OT") is False
        assert term_matches("modular OT available", "OT") is True
        assert term_matches("for or against", "OR") is True   # "or" is its own word
        assert term_matches("doctor or surgeon", "OR") is True
        assert term_matches("rumor mill", "OR") is False
        assert term_matches("ICU bed", "ICU") is True
        assert term_matches("ridiculously good", "ICU") is False

    def test_term_matches_phrases_match_as_phrase(self):
        # multi-word phrase must match as phrase, not interleaved tokens
        assert term_matches("dialysis machine on-site", "dialysis machine") is True
        assert term_matches(
            "machine for dialysis support", "dialysis machine"
        ) is False  # words present but not as phrase

    def test_term_matches_digit_symbol_tokens_word_bounded(self):
        # 24/7 and 24x7 must use word boundaries (avoid matching inside dates / IDs)
        assert term_matches("Open 24/7 with on-call team", "24/7") is True
        assert term_matches("24/7-shift", "24/7") is True   # `-` is non-word, OK
        assert term_matches("v124/7890", "24/7") is False    # bounded by digit
        assert term_matches("24x7 service", "24x7") is True

    def test_find_matching_terms_returns_longest_first(self):
        text = "Trauma centre with a 24/7 ambulance and ER triage"
        terms = ["trauma centre", "trauma", "ambulance", "ER", "24/7"]
        hits = find_matching_terms(text, terms)
        assert "trauma centre" in hits
        assert "ambulance" in hits
        assert "er" in hits
        assert "24/7" in hits
        # Longest first
        assert hits[0] == "trauma centre"


# ---------------------------------------------------------------------------
# 2. Capability detection (taxonomy + intent parser)
# ---------------------------------------------------------------------------

class TestCapabilityDetection:
    """find_capabilities_in_text + parse_query_intent."""

    def test_no_emergency_for_stapler_circumcision(self):
        # The exact bug: "Stapler Circumcision" must not pull in EMERGENCY_TRAUMA
        # via the "ER" substring inside "Stapler".
        assert "EMERGENCY_TRAUMA" not in find_capabilities_in_text(
            "Stapler Circumcision"
        )
        assert "EMERGENCY_TRAUMA" not in find_capabilities_in_text(
            "Cataract Surgery, Refractive Surgery"
        )

    def test_dialysis_query_does_not_trigger_emergency(self):
        # The exact second bug: 'centers' contains 'er', and the old matcher
        # promoted the dialysis-centres query to EMERGENCY_TRAUMA. Must not.
        intent = parse_query_intent("Find dialysis centers in Uttar Pradesh")
        assert "DIALYSIS_RENAL" in intent.capabilities_required
        assert "EMERGENCY_TRAUMA" not in intent.capabilities_required
        assert intent.state == "Uttar Pradesh"

    def test_emergency_query_still_detects_emergency(self):
        # Sanity: the fix must not silence real emergency queries.
        intent = parse_query_intent("Find emergency hospitals in Maharashtra")
        assert "EMERGENCY_TRAUMA" in intent.capabilities_required
        assert intent.state == "Maharashtra"

    def test_capability_taxonomy_dialysis_no_bare_kidney_keyword(self):
        # Bare "kidney" was the over-matching keyword. Confirm it's gone.
        cap = CAPABILITY_INDEX["DIALYSIS_RENAL"]
        keywords_lower = [k.lower() for k in cap["keywords"]]
        assert "kidney" not in keywords_lower
        assert "renal" not in keywords_lower    # too broad on its own

    def test_capability_taxonomy_emergency_strong_terms_clinical(self):
        cap = CAPABILITY_INDEX["EMERGENCY_TRAUMA"]
        strong_lower = {s.lower() for s in cap["strong_evidence_keywords"]}
        # Must include real emergency-presence terms
        assert "ambulance" in strong_lower
        assert "24/7" in strong_lower or "24x7" in strong_lower
        assert "triage" in strong_lower
        assert "resuscitation" in strong_lower
        # Must NOT include over-broad terms
        assert "surgery" not in strong_lower
        assert "treatment" not in strong_lower
        assert "operation" not in strong_lower
        assert "centre" not in strong_lower
        assert "hospital" not in strong_lower


# ---------------------------------------------------------------------------
# 3. Evidence citation safe matching
# ---------------------------------------------------------------------------

class TestEvidenceCitation:
    """extract_evidence_snippets must use safe matching."""

    def test_evidence_skips_stapler_for_emergency(self):
        # Record only mentions stapler / circumcision — there must be zero
        # EMERGENCY_TRAUMA evidence even though "stapler" contains "er".
        record = _facility(
            facility_id="F-STAPLER-1",
            name="Sample Surgical Clinic",
            procedures="Stapler Circumcision; Routine Day-Care Surgery",
            equipment="Stapler kit",
            specialties="General surgery",
        )
        snippets = extract_evidence_snippets(record, ["EMERGENCY_TRAUMA"])
        assert snippets == []

    def test_evidence_real_emergency_text_promotes_strong(self):
        record = _facility(
            facility_id="F-ER-1",
            name="City Trauma Hospital",
            equipment="Trauma bay; Defibrillator; 24/7 Ambulance",
            procedures="Emergency department; ATLS protocol",
            evidence_summary="On-site casualty ward with triage and resuscitation",
        )
        snippets = extract_evidence_snippets(record, ["EMERGENCY_TRAUMA"])
        assert any(s.support_level == "strong" for s in snippets)
        # All snippets we kept must reference EMERGENCY_TRAUMA
        assert all(s.capability_id == "EMERGENCY_TRAUMA" for s in snippets)

    def test_evidence_dialysis_real_machine_strong(self):
        record = _facility(
            facility_id="F-DIA-1",
            name="ABC Dialysis Centre",
            equipment="Haemodialysis machine; RO water plant",
            specialties="Nephrology",
            procedures="Haemodialysis sessions",
        )
        snippets = extract_evidence_snippets(record, ["DIALYSIS_RENAL"])
        assert any(s.support_level == "strong" for s in snippets)
        assert all(s.capability_id == "DIALYSIS_RENAL" for s in snippets)

    def test_evidence_kidney_stones_does_not_trigger_dialysis(self):
        # A urology / kidney-stones-only record must not produce dialysis
        # evidence after Stage 16.
        record = _facility(
            facility_id="F-STONE-1",
            name="Apex Urology Clinic",
            specialties="Urology",
            procedures="Kidney stones removal; Urine analysis; Renal profile lab tests",
            evidence_summary="Stone-clinic services with imaging support",
        )
        snippets = extract_evidence_snippets(record, ["DIALYSIS_RENAL"])
        assert snippets == []


# ---------------------------------------------------------------------------
# 4. Validator strict emergency / dialysis terms
# ---------------------------------------------------------------------------

class TestValidatorStrictTerms:
    def test_emergency_validator_misses_when_only_generic_surgery(self):
        # Cataract surgery / Stapler Circumcision must not validate
        # EMERGENCY_TRAUMA.
        record = _facility(
            facility_id="F-GEN-1",
            name="Generic Day-Care Clinic",
            specialties="Cataract surgery; Stapler Circumcision",
            procedures="Day-care procedures",
            equipment="Stapler; Phaco machine",
        )
        findings = validate_candidate(record, ["EMERGENCY_TRAUMA"], [])
        emerg = [f for f in findings if f.capability == "EMERGENCY_TRAUMA"]
        assert len(emerg) == 1
        # No emergency terms found and no snippets → high-severity missing.
        assert emerg[0].finding_type == "missing_evidence"
        assert emerg[0].severity == "high"

    def test_emergency_validator_passes_with_clinical_terms(self):
        record = _facility(
            facility_id="F-ER-2",
            name="District Emergency Hospital",
            equipment="Ambulance, ventilator, defibrillator",
            procedures="Emergency department triage",
            evidence_summary="24/7 casualty ward with resuscitation bay",
        )
        # Treat snippets as empty — the rule still finds terms in the record.
        findings = validate_candidate(record, ["EMERGENCY_TRAUMA"], [])
        emerg = [f for f in findings if f.capability == "EMERGENCY_TRAUMA"]
        assert len(emerg) == 1
        # Without strong snippets the rule emits weak_evidence (medium),
        # not high-severity missing.
        assert emerg[0].finding_type in {"weak_evidence", "supported"}
        assert emerg[0].severity != "high"

    def test_dialysis_validator_misses_for_homeopathy(self):
        record = _facility(
            facility_id="F-HOMEO-1",
            name="Generic Homoeopathy Clinic",
            specialties="Homoeopathy",
            evidence_summary="Holistic homoeopathic remedies for chronic illness",
        )
        findings = validate_candidate(record, ["DIALYSIS_RENAL"], [])
        dia = [f for f in findings if f.capability == "DIALYSIS_RENAL"]
        assert len(dia) == 1
        assert dia[0].finding_type == "missing_evidence"
        assert dia[0].severity == "high"


# ---------------------------------------------------------------------------
# 5. Local retriever ranking
# ---------------------------------------------------------------------------

class TestLocalRetrieverRanking:
    def test_haemodialysis_outranks_kidney_stones(self):
        df = pd.DataFrame([
            _facility(
                facility_id="F-DIA",
                name="Khurana Dialysis Centre",
                specialties="Nephrology, Dialysis",
                equipment="Haemodialysis machine; RO water plant",
                procedures="Haemodialysis sessions",
            ),
            _facility(
                facility_id="F-STONE",
                name="Apex Urology Clinic",
                specialties="Urology",
                procedures="Kidney stones removal",
            ),
            _facility(
                facility_id="F-HOMEO",
                name="4th Generation Homoeopathy Clinic",
                specialties="Homoeopathy",
            ),
        ])
        intent = parse_query_intent("Find dialysis centers in Uttar Pradesh")
        candidates = retrieve_local_candidates(df, intent)
        ids = [c.facility_id for c in candidates]
        # The dialysis facility must be first.
        assert ids[0] == "F-DIA"
        # And homeopathy must NOT outrank it.
        assert ids.index("F-DIA") < ids.index("F-HOMEO")

    def test_name_match_boost_for_dialysis(self):
        # Two records with the same evidence content — only the name
        # mentions "Dialysis". The named one must win.
        df = pd.DataFrame([
            _facility(
                facility_id="F-NAMED",
                name="Sunrise Dialysis Centre",
                specialties="General medicine",
            ),
            _facility(
                facility_id="F-PLAIN",
                name="Sunrise General Clinic",
                specialties="General medicine",
            ),
        ])
        intent = parse_query_intent("Find dialysis centres in Uttar Pradesh")
        candidates = retrieve_local_candidates(df, intent)
        assert candidates[0].facility_id == "F-NAMED"
        assert candidates[0].local_relevance_score > candidates[1].local_relevance_score


# ---------------------------------------------------------------------------
# 6. Recommendation engine — Tavily interpretation note
# ---------------------------------------------------------------------------

class TestTavilyInterpretation:
    def test_identity_only_verification_message(self):
        # web verification with empty matched_capability ⇒ identity-only
        # phrasing must appear in reason and in human_next_steps.
        candidate = {
            "raw_record": {
                "facility_id": "F-ID-ONLY",
                "trust_score": 0.7,
                "trust_category": "Reasonable",
                "recommendation_readiness": "Usable with verification",
            },
            "matched_capabilities": [],
            "evidence_snippets": [],
            "validation_findings": [],
            "vector_similarity": None,
            "web_verification": WebVerificationResult(
                facility_id="F-ID-ONLY",
                verification_status="verified",
                verification_score=0.7,
                matched_capability=[],   # empty = identity-only
                matched_name="Sunrise Hospital",
                matched_location="Lucknow, Uttar Pradesh",
                top_url="https://example.org/sunrise",
                top_snippet="Sunrise Hospital, Lucknow.",
            ),
        }
        intent = parse_query_intent("Find dialysis centres in Uttar Pradesh")
        reason = engine._build_reason_for_recommendation(candidate, intent)
        steps = engine._build_human_next_steps(candidate, intent)
        assert "identity" in reason.lower()
        assert any("identity" in s.lower() for s in steps)

    def test_capability_verified_message(self):
        candidate = {
            "raw_record": {
                "facility_id": "F-CAP",
                "trust_score": 0.7,
                "trust_category": "Reasonable",
                "recommendation_readiness": "Usable with verification",
            },
            "matched_capabilities": ["DIALYSIS_RENAL"],
            "evidence_snippets": [],
            "validation_findings": [],
            "vector_similarity": None,
            "web_verification": WebVerificationResult(
                facility_id="F-CAP",
                verification_status="verified",
                verification_score=0.8,
                matched_capability=["DIALYSIS_RENAL"],
                matched_name="Khurana Dialysis Centre",
                matched_location="Lucknow, Uttar Pradesh",
                top_url="https://example.org/dialysis",
                top_snippet="Haemodialysis services at Khurana Dialysis Centre.",
            ),
        }
        intent = parse_query_intent("Find dialysis centres in Uttar Pradesh")
        reason = engine._build_reason_for_recommendation(candidate, intent)
        steps = engine._build_human_next_steps(candidate, intent)
        assert "DIALYSIS_RENAL" in reason
        # Identity-only phrasing must NOT appear when caps are matched.
        assert "identity" not in reason.lower()
        assert all("identity" not in s.lower() for s in steps)


# ---------------------------------------------------------------------------
# 7. End-to-end recommendation check
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_dialysis_query_top_recommendation_is_dialysis_facility(self):
        df = pd.DataFrame([
            _facility(
                facility_id="F-DIA",
                name="Khurana Dialysis Centre",
                specialties="Nephrology, Dialysis",
                equipment="Haemodialysis machine; RO water plant",
                procedures="Haemodialysis sessions",
                trust_score=0.74,
                readiness="Ready for recommendation",
            ),
            _facility(
                facility_id="F-HOMEO",
                name="4th Generation Homoeopathy Clinic",
                specialties="Homoeopathy",
                trust_score=0.87,
                readiness="Ready for recommendation",
            ),
        ])

        # Stub the Settings singleton so we never reach Databricks/Tavily
        # in an isolated unit test.
        with patch.object(engine, "_get_settings") as mock_settings:
            mock_settings.return_value.vector_search_enabled = False
            mock_settings.return_value.tavily_enabled = False
            mock_settings.return_value.tavily_api_key = ""
            mock_settings.return_value.tavily_default_depth = "basic"
            mock_settings.return_value.tavily_max_web_verified = 0

            response = engine.run_recommendation(
                query="Find dialysis centers in Uttar Pradesh",
                facilities_df=df,
                max_results=2,
                enable_web_verification=False,
                enable_vector_search=False,
            )

        # The intent must not have leaked EMERGENCY_TRAUMA.
        assert "EMERGENCY_TRAUMA" not in response.intent.capabilities_required
        assert response.recommendations, "expected at least one recommendation"
        # The dialysis facility must be top.
        assert response.recommendations[0].facility_id == "F-DIA"
