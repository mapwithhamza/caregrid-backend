from __future__ import annotations
import math
from agent_core.schemas import EvidenceSnippet


def _clean_value(val) -> str:
    """
    Return a clean string representation of val.
    Maps None, NaN (float/numpy), empty strings, and null-like text to "".
    Unwraps list-like strings: "['ICU', 'dialysis']" → "ICU, dialysis".
    """
    if val is None:
        return ""
    # Numeric NaN — covers float('nan') and numpy.nan
    try:
        if math.isnan(float(val)):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    if not s or s.lower() in ("none", "nan", "null", "n/a", "na", "<na>", "nat"):
        return ""
    # Unwrap list-like strings produced by str(list) or CSV export
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].replace("'", "").replace('"', "")
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        return ", ".join(parts)
    return s


def build_combined_evidence(record: dict) -> str:
    """
    Combine all clinical fields from a facility record into a single, labelled
    evidence text block suitable for storage in combined_medical_evidence.

    Fields consumed (in order):
        name, facility_type, city, state, specialties, procedures,
        equipment, capabilities_raw, evidence_summary, combined_medical_evidence

    Returns an empty string when all fields are absent or null.
    """
    name       = _clean_value(record.get("name"))
    ftype      = _clean_value(record.get("facility_type"))
    city       = _clean_value(record.get("city"))
    state      = _clean_value(record.get("state"))
    specs      = _clean_value(record.get("specialties"))
    procs      = _clean_value(record.get("procedures"))
    equip      = _clean_value(record.get("equipment"))
    caps       = _clean_value(record.get("capabilities_raw"))
    summary    = _clean_value(record.get("evidence_summary"))
    evidence   = _clean_value(record.get("combined_medical_evidence"))

    parts: list[str] = []
    if name:
        parts.append(f"Facility: {name}")
    if ftype:
        parts.append(f"Type: {ftype}")
    loc = ", ".join(filter(None, [city, state]))
    if loc:
        parts.append(f"Location: {loc}")
    if specs:
        parts.append(f"Specialties: {specs}")
    if procs:
        parts.append(f"Procedures: {procs}")
    if equip:
        parts.append(f"Equipment: {equip}")
    if caps:
        parts.append(f"Capabilities: {caps}")
    if summary:
        parts.append(f"Summary: {summary}")
    if evidence:
        parts.append(f"Evidence: {evidence}")

    return "\n".join(parts)


def build_evidence(
    facility_id: str,
    combined_medical_evidence,  # str | None — accepts None/NaN safely
) -> list[EvidenceSnippet]:
    """
    Return a single EvidenceSnippet from combined_medical_evidence text.
    Truncates to 500 characters. Returns [] for null/empty input.
    """
    text = _clean_value(combined_medical_evidence)
    if not text:
        return []
    return [EvidenceSnippet(facility_id=facility_id, excerpt=text[:500])]


def build_evidence_from_record(record: dict) -> list[EvidenceSnippet]:
    """
    Build EvidenceSnippet list from a full facility record dict.
    Combines all clinical fields via build_combined_evidence.
    Returns [] when facility_id is absent or all fields are empty.
    """
    facility_id = _clean_value(record.get("facility_id"))
    if not facility_id:
        return []
    combined = build_combined_evidence(record)
    if not combined:
        return []
    return [EvidenceSnippet(facility_id=facility_id, excerpt=combined[:500])]
