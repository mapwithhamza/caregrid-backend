"""
agent_core.validator — Self-correction layer for facility candidates.

Given a parsed `AgentIntent` and a single candidate facility record,
`validate_candidate()` answers the question:

  "Is the agent allowed to claim this facility supports each requested
   capability, and if so how confidently?"

The output is a list of `ValidationFinding` rows, one per requested
capability (plus optional contradiction findings). Each finding carries:

  * `finding_type` — `supported` | `weak_evidence` | `missing_evidence` | `contradiction`
  * `severity`     — `info` | `low` | `medium` | `high`
  * `evidence_used`     — excerpts of the snippets that support the claim
  * `missing_evidence`  — concrete terms the rule expected but couldn't find
  * `recommendation_impact` — what the recommender should do with this row

Per-capability rules (Stage 11)
-------------------------------
The 6 capabilities below have explicit term lists; other capabilities are
silently skipped (no finding emitted) so the validator stays opt-in:

  * ICU_CRITICAL_CARE   → ventilator, ICU bed, intensive care unit, intensivist, …
  * SURGERY             → operation theatre, OT, anaesthesia, surgeon, …
  * DIALYSIS_RENAL      → dialysis machine, hemodialysis, nephrology, CRRT, …
  * ONCOLOGY            → oncologist, chemotherapy, radiation, linear accelerator, …
  * EMERGENCY_TRAUMA    → ambulance, casualty, trauma, 24/7, oxygen, …
  * NEONATAL_PEDIATRIC  → incubator, warmer, neonatal ventilator, NICU, neonatologist, …

Decision matrix
---------------
For each requested capability:

  +-----------------------------+--------------------+--------+----------------------------+
  | snippet evidence            | term presence      | level  | impact                     |
  +-----------------------------+--------------------+--------+----------------------------+
  | at least one strong snippet | any                | info   | none                       |
  | only moderate/weak snippets | any                | medium | downgrade_to_verify_before |
  | no snippets                 | some terms found   | medium | downgrade_to_verify_before |
  | no snippets                 | no terms found     | high   | do_not_recommend           |
  +-----------------------------+--------------------+--------+----------------------------+

Contradictions detected by `agent_core.contradiction_rules` are appended
to the findings list with `finding_type="contradiction"` and
`recommendation_impact="flag_for_review"`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent_core.capability_taxonomy import term_matches
from agent_core.contradiction_rules import find_contradictions
from agent_core.schemas import AgentResponse, EvidenceSnippet, ValidationFinding


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Allowed values for finding_type / recommendation_impact / severity.
FINDING_SUPPORTED        = "supported"
FINDING_WEAK_EVIDENCE    = "weak_evidence"
FINDING_MISSING_EVIDENCE = "missing_evidence"
FINDING_CONTRADICTION    = "contradiction"

IMPACT_NONE                          = "none"
IMPACT_DOWNGRADE_TO_VERIFY_BEFORE_USE = "downgrade_to_verify_before_use"
IMPACT_DO_NOT_RECOMMEND              = "do_not_recommend"
IMPACT_FLAG_FOR_REVIEW               = "flag_for_review"

SEVERITY_INFO   = "info"
SEVERITY_LOW    = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH   = "high"

# Fields searched when checking for term presence on the record.
_RECORD_SEARCH_FIELDS: list[str] = [
    "name",
    "specialties",
    "procedures",
    "equipment",
    "capabilities_raw",
    "evidence_summary",
    "combined_medical_evidence",
    "required_staff",
]

_NULLISH_TOKENS = {"", "none", "nan", "null", "n/a", "na", "<na>", "nat"}

# How many terms / excerpts to surface in each finding (audit-log readability).
_MAX_TERMS_TO_SURFACE = 6
_MAX_EVIDENCE_EXCERPTS = 3


# ---------------------------------------------------------------------------
# Per-capability rule definitions
# ---------------------------------------------------------------------------
# Each rule names the capability ID, a short rule_id (audit-log friendly),
# a display name, and the term list used to check whether the facility's
# record contains supporting evidence. Term lists deliberately err on the
# side of including a few extra related items (e.g. cardiac monitor for ICU)
# so that real-world phrasing variation is tolerated.
# ---------------------------------------------------------------------------

VALIDATION_RULES: dict[str, dict[str, Any]] = {
    "ICU_CRITICAL_CARE": {
        "rule_id": "VAL_ICU",
        "display_name": "ICU / Critical Care",
        "required_evidence_terms": [
            "ventilator", "mechanical ventilation",
            "ICU bed", "ICU", "ICCU", "MICU", "SICU",
            "intensive care unit", "intensive care", "critical care",
            "intensivist", "vasopressor", "arterial line",
            "cardiac monitor", "defibrillator", "oxygen",
        ],
    },
    "SURGERY": {
        "rule_id": "VAL_SURGERY",
        "display_name": "Surgery / Operation Theatre",
        "required_evidence_terms": [
            "operation theatre", "operation theater", "modular OT", "OT",
            "anaesthesia", "anesthesia", "anaesthesiologist", "anesthesiologist",
            "surgeon", "surgical procedure", "surgical equipment",
            "laparoscopy", "laparoscopic", "robotic surgery",
            "anaesthesia machine", "electrosurgical unit",
        ],
    },
    "DIALYSIS_RENAL": {
        # Stage 16: term list matches the tightened taxonomy. Bare
        # "kidney" was never here (good), and "renal" alone is still
        # excluded because it substring-matches "adrenal" / "renal
        # profile". Specific phrases ("renal unit", "renal dialysis")
        # are kept.
        "rule_id": "VAL_DIALYSIS",
        "display_name": "Dialysis / Renal Care",
        "required_evidence_terms": [
            "dialysis", "dialysis machine", "haemodialysis machine",
            "hemodialysis machine", "hemodialysis unit", "haemodialysis unit",
            "hemodialysis", "haemodialysis", "renal dialysis",
            "kidney dialysis", "peritoneal dialysis",
            "nephrology", "nephrologist",
            "renal unit", "renal care",
            "AV fistula", "arteriovenous fistula",
            "CRRT", "continuous renal replacement therapy",
            "RO water plant", "dialysis chair", "dialysis procedure",
        ],
    },
    "ONCOLOGY": {
        "rule_id": "VAL_ONCOLOGY",
        "display_name": "Oncology / Cancer Care",
        "required_evidence_terms": [
            "oncologist", "chemotherapy", "chemo",
            "radiotherapy", "radiation oncology", "radiation therapy", "radiation",
            "cancer treatment", "oncology",
            "linear accelerator", "LINAC", "PET-CT", "brachytherapy",
        ],
    },
    "EMERGENCY_TRAUMA": {
        # Stage 16: tightened to only clinically meaningful emergency
        # tokens. Bare "oxygen" and "critical support" were removed
        # because every minor surgical clinic has an oxygen cylinder —
        # they cannot, on their own, validate an emergency claim. "ER"
        # is added explicitly; the matcher word-bounds short tokens so
        # it cannot leak inside "centers" / "stapler" / etc.
        "rule_id": "VAL_EMERGENCY",
        "display_name": "Emergency / Trauma",
        "required_evidence_terms": [
            "ambulance", "casualty", "casualty ward",
            "trauma", "trauma bay", "trauma centre", "trauma center",
            "emergency department", "emergency room", "emergency", "ER",
            "A&E", "ATLS", "resuscitation", "resuscitation bay",
            "24/7", "24x7", "round the clock",
            "oxygen support", "ventilator", "critical care", "triage",
        ],
    },
    "NEONATAL_PEDIATRIC": {
        "rule_id": "VAL_NEONATAL",
        "display_name": "Neonatal / Paediatric Care",
        "required_evidence_terms": [
            "incubator", "warmer", "neonatal ventilator",
            "NICU bed", "NICU", "PICU",
            "neonatologist", "neonatal nurse",
            "phototherapy", "neonatal resuscitation",
            "preterm care", "surfactant therapy",
        ],
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _stringify(val: Any) -> str:
    """Render a cell value as a stripped string. Returns '' for null-ish."""
    if val is None:
        return ""
    try:
        if isinstance(val, float) and pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    if s.lower() in _NULLISH_TOKENS:
        return ""
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].replace("'", "").replace('"', "")
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        return ", ".join(parts)
    return s


def _record_search_text(record: dict) -> str:
    """Build a single lowercased blob covering all field-of-interest text."""
    chunks: list[str] = []
    for field in _RECORD_SEARCH_FIELDS:
        text = _stringify(record.get(field))
        if text:
            chunks.append(text)
    return " | ".join(chunks).lower()


def _term_present(term: str, text_lower: str) -> bool:
    """
    Case-insensitive presence check using the shared safe-matching
    helper from :mod:`agent_core.capability_taxonomy`.

    Short tokens (≤ 3 chars) and any token containing a digit / ``/`` /
    ``x`` / ``:`` / ``&`` are matched with strict word boundaries so
    that ``ER`` cannot match inside ``"Stapler Circumcision"`` or
    ``"centers"``, and ``24/7`` cannot match inside a longer date.

    Stage 16: previously had its own duplicate regex; now delegates to
    :func:`term_matches` for a single source of truth.
    """
    return term_matches(text_lower, term)


def _split_snippets_by_level(
    snippets: list[EvidenceSnippet],
) -> tuple[list[EvidenceSnippet], list[EvidenceSnippet]]:
    """Return (strong_snippets, moderate_or_weak_snippets)."""
    strong = [s for s in snippets if s.support_level == "strong"]
    weak = [s for s in snippets if s.support_level in ("moderate", "weak")]
    return strong, weak


# ---------------------------------------------------------------------------
# Per-capability validation
# ---------------------------------------------------------------------------

def _validate_capability(
    *,
    facility_id: str,
    capability_id: str,
    rule: dict[str, Any],
    snippets_for_cap: list[EvidenceSnippet],
    record_text_lower: str,
) -> ValidationFinding:
    """Apply one capability rule and emit one `ValidationFinding`."""
    strong, weak = _split_snippets_by_level(snippets_for_cap)

    required = rule["required_evidence_terms"]
    terms_found   = [t for t in required if _term_present(t, record_text_lower)]
    terms_missing = [t for t in required if t not in terms_found]
    display       = rule["display_name"]
    rule_id       = rule["rule_id"]

    if strong:
        return ValidationFinding(
            facility_id=facility_id,
            rule=rule_id,
            severity=SEVERITY_INFO,
            message=(
                f"{display} claim is supported by strong evidence in the "
                f"facility record."
            ),
            capability=capability_id,
            finding_type=FINDING_SUPPORTED,
            evidence_used=[s.excerpt for s in strong[:_MAX_EVIDENCE_EXCERPTS]],
            missing_evidence=[],
            recommendation_impact=IMPACT_NONE,
        )

    if weak or terms_found:
        evidence_excerpts = [s.excerpt for s in weak[:_MAX_EVIDENCE_EXCERPTS]]
        return ValidationFinding(
            facility_id=facility_id,
            rule=rule_id,
            severity=SEVERITY_MEDIUM,
            message=(
                f"{display} claim has only moderate or weak supporting "
                f"evidence — verify before recommending."
            ),
            capability=capability_id,
            finding_type=FINDING_WEAK_EVIDENCE,
            evidence_used=evidence_excerpts,
            missing_evidence=terms_missing[:_MAX_TERMS_TO_SURFACE],
            recommendation_impact=IMPACT_DOWNGRADE_TO_VERIFY_BEFORE_USE,
        )

    # No snippets, no terms — claim is unsupported.
    return ValidationFinding(
        facility_id=facility_id,
        rule=rule_id,
        severity=SEVERITY_HIGH,
        message=(
            f"{display} claim has no supporting evidence in the facility "
            f"record. The agent must not recommend on this basis alone."
        ),
        capability=capability_id,
        finding_type=FINDING_MISSING_EVIDENCE,
        evidence_used=[],
        missing_evidence=required[:_MAX_TERMS_TO_SURFACE],
        recommendation_impact=IMPACT_DO_NOT_RECOMMEND,
    )


# ---------------------------------------------------------------------------
# Public API — validate_candidate
# ---------------------------------------------------------------------------

def validate_candidate(
    record: dict,
    requested_capabilities: list[str],
    evidence_snippets: list[EvidenceSnippet],
) -> list[ValidationFinding]:
    """
    Run capability and contradiction validation on a single facility record.

    Parameters
    ----------
    record:
        Facility record as a dict (e.g. `pandas.Series.to_dict()`). Must
        contain `facility_id`. Missing or null fields are tolerated.
    requested_capabilities:
        List of capability IDs the agent intends to claim. Capability IDs
        not in `VALIDATION_RULES` are silently skipped.
    evidence_snippets:
        Snippets returned by `agent_core.evidence_citation.extract_evidence_snippets()`.
        Each snippet's `capability_id` is used to group it.

    Returns
    -------
    list[ValidationFinding]
        - Zero or one finding per requested capability (only the 6 known
          capabilities produce findings).
        - Plus zero or more contradiction findings appended at the end.
    """
    findings: list[ValidationFinding] = []
    if not record:
        return findings

    facility_id = str(record.get("facility_id") or "")
    record_text_lower = _record_search_text(record)

    # Group snippets by capability_id for fast lookup.
    snippets_by_cap: dict[str, list[EvidenceSnippet]] = {}
    for s in evidence_snippets or []:
        if s.capability_id:
            snippets_by_cap.setdefault(s.capability_id, []).append(s)

    # Per-capability findings (input order preserved).
    seen_caps: set[str] = set()
    for cap_id in requested_capabilities or []:
        if cap_id in seen_caps:
            continue
        seen_caps.add(cap_id)
        rule = VALIDATION_RULES.get(cap_id)
        if not rule:
            continue
        finding = _validate_capability(
            facility_id=facility_id,
            capability_id=cap_id,
            rule=rule,
            snippets_for_cap=snippets_by_cap.get(cap_id, []),
            record_text_lower=record_text_lower,
        )
        findings.append(finding)

    # Contradiction findings — appended after capability findings.
    for c in find_contradictions(record):
        findings.append(ValidationFinding(
            facility_id=facility_id,
            rule=c["id"],
            severity=c.get("severity", SEVERITY_HIGH),
            message=f"Contradiction: {c['description']}",
            capability=None,
            finding_type=FINDING_CONTRADICTION,
            evidence_used=[],
            missing_evidence=[],
            recommendation_impact=IMPACT_FLAG_FOR_REVIEW,
        ))

    return findings


# ---------------------------------------------------------------------------
# Backward-compatibility — response-level validator
# ---------------------------------------------------------------------------

def validate_response(response: AgentResponse) -> list[str]:
    """
    Quick high-level sanity check on the final `AgentResponse`. Kept for
    backward compatibility with the original Stage-1 tests; new code
    should use `validate_candidate()`.
    """
    warnings: list[str] = []
    if not response.evidence:
        warnings.append("No evidence blocks returned.")
    if not response.reasoning:
        warnings.append("Missing reasoning field.")
    if not response.safety_note:
        warnings.append("Missing safety_note field.")
    return warnings
