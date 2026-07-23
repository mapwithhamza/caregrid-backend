import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core.capability_taxonomy import (
    get_capability,
    list_capabilities,
    find_capabilities_in_text,
    get_high_acuity_capabilities,
    CAPABILITY_INDEX,
)

REQUIRED_CAPABILITY_IDS = [
    "ICU_CRITICAL_CARE",
    "OXYGEN_SUPPORT",
    "EMERGENCY_TRAUMA",
    "SURGERY",
    "DIALYSIS_RENAL",
    "ONCOLOGY",
    "MATERNAL_CARE",
    "NEONATAL_PEDIATRIC",
    "DIAGNOSTICS",
    "AMBULANCE",
    "BLOOD_BANK",
    "TWENTY_FOUR_SEVEN",
    "SPECIALIST_SUPPORT",
]


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------

def test_all_required_capabilities_exist():
    defined = list_capabilities()
    for cap_id in REQUIRED_CAPABILITY_IDS:
        assert cap_id in defined, f"Missing capability: {cap_id}"


def test_capability_count():
    assert len(list_capabilities()) == 13


def test_each_capability_has_required_fields():
    required_fields = [
        "capability_id", "display_name", "keywords", "synonyms",
        "strong_evidence_keywords", "supporting_equipment",
        "required_staff", "high_acuity", "web_search_terms",
    ]
    for cap_id in list_capabilities():
        cap = get_capability(cap_id)
        for field in required_fields:
            assert field in cap, f"{cap_id} missing field: {field}"


def test_capability_index_matches_list():
    assert set(CAPABILITY_INDEX.keys()) == set(list_capabilities())


# ---------------------------------------------------------------------------
# ICU_CRITICAL_CARE
# ---------------------------------------------------------------------------

def test_icu_has_ventilator_keyword():
    cap = get_capability("ICU_CRITICAL_CARE")
    all_terms = cap["keywords"] + cap["synonyms"] + cap["strong_evidence_keywords"]
    assert any("ventilator" in t.lower() for t in all_terms)


def test_icu_has_oxygen_term():
    cap = get_capability("ICU_CRITICAL_CARE")
    all_terms = cap["keywords"] + cap["synonyms"] + cap["strong_evidence_keywords"]
    assert any("critical care" in t.lower() for t in all_terms)


def test_icu_is_high_acuity():
    assert get_capability("ICU_CRITICAL_CARE")["high_acuity"] is True


def test_icu_detected_in_text():
    assert "ICU_CRITICAL_CARE" in find_capabilities_in_text("ICU with ventilator support")
    assert "ICU_CRITICAL_CARE" in find_capabilities_in_text("intensive care unit beds")
    assert "ICU_CRITICAL_CARE" in find_capabilities_in_text("critical care beds available")


# ---------------------------------------------------------------------------
# DIALYSIS_RENAL
# ---------------------------------------------------------------------------

def test_dialysis_has_dialysis_machine_keyword():
    cap = get_capability("DIALYSIS_RENAL")
    strong = cap["strong_evidence_keywords"]
    assert any("dialysis machine" in t.lower() for t in strong)


def test_dialysis_has_hemodialysis_keyword():
    cap = get_capability("DIALYSIS_RENAL")
    all_terms = cap["keywords"] + cap["synonyms"] + cap["strong_evidence_keywords"]
    assert any("hemodialysis" in t.lower() for t in all_terms)


def test_dialysis_is_high_acuity():
    assert get_capability("DIALYSIS_RENAL")["high_acuity"] is True


def test_dialysis_detected_in_text():
    assert "DIALYSIS_RENAL" in find_capabilities_in_text("dialysis unit available")
    assert "DIALYSIS_RENAL" in find_capabilities_in_text("hemodialysis machine installed")
    assert "DIALYSIS_RENAL" in find_capabilities_in_text("renal replacement therapy ward")


# ---------------------------------------------------------------------------
# ONCOLOGY
# ---------------------------------------------------------------------------

def test_oncology_has_cancer_keyword():
    cap = get_capability("ONCOLOGY")
    assert any("cancer" in t.lower() for t in cap["keywords"])


def test_oncology_has_chemotherapy_keyword():
    cap = get_capability("ONCOLOGY")
    assert any("chemotherapy" in t.lower() for t in cap["keywords"])


def test_oncology_is_high_acuity():
    assert get_capability("ONCOLOGY")["high_acuity"] is True


def test_oncology_detected_in_text():
    assert "ONCOLOGY" in find_capabilities_in_text("cancer treatment centre")
    assert "ONCOLOGY" in find_capabilities_in_text("chemotherapy ward available")
    assert "ONCOLOGY" in find_capabilities_in_text("radiation oncology department")


# ---------------------------------------------------------------------------
# NEONATAL_PEDIATRIC
# ---------------------------------------------------------------------------

def test_neonatal_has_incubator_equipment():
    cap = get_capability("NEONATAL_PEDIATRIC")
    assert any("incubator" in e.lower() for e in cap["supporting_equipment"])


def test_neonatal_is_high_acuity():
    assert get_capability("NEONATAL_PEDIATRIC")["high_acuity"] is True


def test_neonatal_detected_in_text():
    assert "NEONATAL_PEDIATRIC" in find_capabilities_in_text("NICU with 10 incubators")
    assert "NEONATAL_PEDIATRIC" in find_capabilities_in_text("neonatal care unit")
    assert "NEONATAL_PEDIATRIC" in find_capabilities_in_text("paediatric ICU ward")


# ---------------------------------------------------------------------------
# High-acuity list
# ---------------------------------------------------------------------------

def test_high_acuity_includes_icu():
    assert "ICU_CRITICAL_CARE" in get_high_acuity_capabilities()


def test_high_acuity_includes_emergency():
    assert "EMERGENCY_TRAUMA" in get_high_acuity_capabilities()


def test_high_acuity_includes_dialysis():
    assert "DIALYSIS_RENAL" in get_high_acuity_capabilities()


def test_high_acuity_includes_oncology():
    assert "ONCOLOGY" in get_high_acuity_capabilities()


def test_high_acuity_includes_neonatal():
    assert "NEONATAL_PEDIATRIC" in get_high_acuity_capabilities()


def test_high_acuity_count():
    # ICU, EMERGENCY_TRAUMA, DIALYSIS_RENAL, ONCOLOGY, NEONATAL_PEDIATRIC = 5
    assert len(get_high_acuity_capabilities()) == 5


def test_low_acuity_capabilities_excluded():
    high = set(get_high_acuity_capabilities())
    for cap_id in ["OXYGEN_SUPPORT", "SURGERY", "MATERNAL_CARE", "DIAGNOSTICS",
                   "AMBULANCE", "BLOOD_BANK", "TWENTY_FOUR_SEVEN", "SPECIALIST_SUPPORT"]:
        assert cap_id not in high, f"{cap_id} should not be high acuity"


# ---------------------------------------------------------------------------
# find_capabilities_in_text — edge cases
# ---------------------------------------------------------------------------

def test_find_capabilities_empty_text():
    assert find_capabilities_in_text("") == []


def test_find_capabilities_case_insensitive():
    assert "DIALYSIS_RENAL" in find_capabilities_in_text("DIALYSIS centre available")
    assert "ONCOLOGY" in find_capabilities_in_text("CANCER TREATMENT HOSPITAL")


def test_find_capabilities_no_duplicates():
    result = find_capabilities_in_text("ICU intensive care ventilator critical care")
    assert result.count("ICU_CRITICAL_CARE") == 1


def test_get_capability_raises_for_unknown():
    try:
        get_capability("NONEXISTENT_CAPABILITY")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass
