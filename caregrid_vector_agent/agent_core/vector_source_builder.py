from __future__ import annotations
import pandas as pd
from agent_core.evidence_builder import _clean_value, build_combined_evidence

# ---------------------------------------------------------------------------
# Canonical output column order for the vector source table
# ---------------------------------------------------------------------------
OUTPUT_COLUMNS: list[str] = [
    "facility_id",
    "name",
    "city",
    "state",
    "facility_type",
    "latitude",
    "longitude",
    "trust_score",
    "trust_category",
    "recommendation_readiness",
    "vector_text",
    "combined_medical_evidence",
    "evidence_summary",
]

# Defaults applied when a column is missing from the input DataFrame.
# facility_id and vector_text are intentionally absent — they must come from
# the input data or be computed, never silently defaulted.
_COLUMN_DEFAULTS: dict = {
    "name":                    "",
    "city":                    "",
    "state":                   "",
    "facility_type":           "",
    "latitude":                None,
    "longitude":               None,
    "trust_score":             0.0,
    "trust_category":          "",
    "recommendation_readiness": "",
    "combined_medical_evidence": "",
    "evidence_summary":        "",
}


def build_vector_text(record: dict) -> str:
    """
    Build a semantic-retrieval-optimised text string from a facility record.

    Structure (pipe-delimited sections, each section only emitted if non-empty):
        <name> | <facility_type> | <city>, <state> | <specialties> |
        <procedures> | <equipment> | <capabilities_raw> |
        <evidence_summary> | <combined_medical_evidence>

    Optimised for embedding models: high keyword density, no redundant labels,
    no null/NaN noise.
    """
    name     = _clean_value(record.get("name"))
    ftype    = _clean_value(record.get("facility_type"))
    city     = _clean_value(record.get("city"))
    state    = _clean_value(record.get("state"))
    specs    = _clean_value(record.get("specialties"))
    procs    = _clean_value(record.get("procedures"))
    equip    = _clean_value(record.get("equipment"))
    caps     = _clean_value(record.get("capabilities_raw"))
    summary  = _clean_value(record.get("evidence_summary"))
    evidence = _clean_value(record.get("combined_medical_evidence"))

    sections: list[str] = []

    # Facility identity
    identity = " | ".join(filter(None, [name, ftype]))
    if identity:
        sections.append(identity)

    # Location
    location = ", ".join(filter(None, [city, state]))
    if location:
        sections.append(location)

    # Clinical content — each field as its own section
    for content in [specs, procs, equip, caps]:
        if content:
            sections.append(content)

    # Evidence narrative
    for ev in [summary, evidence]:
        if ev:
            sections.append(ev)

    return " | ".join(sections)


def prepare_vector_source_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare a Databricks-ready vector source DataFrame from raw facility data.

    Steps
    -----
    1. Validate that ``facility_id`` is present and fully populated.
    2. Add any missing output columns with safe defaults.
    3. Build ``combined_medical_evidence`` for rows where it is absent or empty,
       using ``build_combined_evidence`` over all available clinical fields.
    4. Build ``vector_text`` for every row via ``build_vector_text``.
    5. Return a DataFrame with exactly the columns in ``OUTPUT_COLUMNS``
       (columns that are still absent after step 2 are omitted gracefully).

    Parameters
    ----------
    df:
        Raw facility DataFrame. Must contain a ``facility_id`` column with no
        null values.

    Raises
    ------
    ValueError
        If ``facility_id`` column is missing or contains null values.
    """
    if "facility_id" not in df.columns:
        raise ValueError(
            "Input DataFrame must contain a 'facility_id' column."
        )
    if df["facility_id"].isna().any():
        raise ValueError(
            "Input DataFrame contains rows with null facility_id."
        )

    df = df.copy()

    # Add missing columns with safe defaults
    for col, default in _COLUMN_DEFAULTS.items():
        if col not in df.columns:
            df[col] = default

    # Build combined_medical_evidence for rows where it is absent or empty
    cme = "combined_medical_evidence"
    empty_mask = (
        df[cme].isna()
        | (df[cme].astype(str).str.strip() == "")
        | df[cme].astype(str).str.lower().isin(["none", "nan", "<na>"])
    )
    if empty_mask.any():
        df.loc[empty_mask, cme] = (
            df[empty_mask]
            .apply(lambda row: build_combined_evidence(row.to_dict()), axis=1)
        )

    # Build vector_text for every row
    df["vector_text"] = df.apply(
        lambda row: build_vector_text(row.to_dict()), axis=1
    )

    # Return only the canonical output columns that exist in df
    present = [c for c in OUTPUT_COLUMNS if c in df.columns]
    return df[present]
