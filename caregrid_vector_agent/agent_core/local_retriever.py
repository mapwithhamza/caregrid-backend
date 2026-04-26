"""
agent_core.local_retriever — In-memory pandas keyword fallback retriever.

This module is the agent's *guaranteed* retrieval path. It needs no
Databricks, no embedding model, no network — it works against an
in-memory `pandas.DataFrame` of facility records.

The orchestrator calls `VectorRetriever(...).search(...)` first; if the
response is `available=False` (or returns no hits), it falls back to
`retrieve_local_candidates()` here.

Pipeline
--------
1. **Strict filter** by `state`, `facility_type`, and `min_trust_score`
   pulled off the parsed `AgentIntent`.
2. If the strict filter returns zero rows, **relax** in this fixed order:
     a. drop the trust-score floor,
     b. drop the facility-type filter.
   `state` is **not** relaxed unless the caller explicitly opts in via
   `allow_state_relaxation=True`.
3. **Score** the surviving rows by counting capability-keyword hits
   across six text columns:
     specialties, procedures, equipment, capabilities_raw,
     evidence_summary, combined_medical_evidence.
4. **Rank** by `local_relevance_score` desc, then `trust_score` desc as
   tiebreaker. Truncate to `limit_pool`.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, Field

from agent_core.capability_taxonomy import (
    CAPABILITY_INDEX,
    find_matching_terms,
    term_matches,
)
from agent_core.schemas import AgentIntent


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Columns scanned for capability-term hits, in order. Missing columns are
# silently skipped — the retriever degrades gracefully against partial schemas.
SEARCH_FIELDS: list[str] = [
    "specialties",
    "procedures",
    "equipment",
    "capabilities_raw",
    "evidence_summary",
    "combined_medical_evidence",
]

# Per-hit weights. A "hit" is a (term, field) pair: a single term that
# appears in N fields contributes N hits.
WEIGHT_KEYWORD          = 1.0
WEIGHT_SYNONYM          = 1.0
WEIGHT_STRONG_EVIDENCE  = 2.0
# Bonus added once when at least one term from a given capability matched.
WEIGHT_CAPABILITY_BONUS = 0.5
# Stage 16: name-match boost. Awarded once per requested capability when
# any of that capability's keywords / synonyms appears in the facility's
# name field. Lifts e.g. "Dr. Mudit Khurana Dialysis Centre" above
# "4th Generation Homoeopathy Clinic" for a "find dialysis centres"
# query, where both rows pass the state filter but only the first is
# clinically relevant.
WEIGHT_NAME_MATCH       = 3.0

# Tokens that mean "this cell is empty" — match the contract used by
# `evidence_builder._clean_value()` and `vector_source_builder._clean()`.
_NULLISH_TOKENS = {"", "none", "nan", "null", "n/a", "na", "<na>", "nat"}


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

class LocalCandidate(BaseModel):
    """One ranked candidate returned by the local retriever."""
    facility_id: str
    raw_record: dict[str, Any] = Field(default_factory=dict)
    matched_fields: list[str] = Field(default_factory=list)
    matched_capabilities: list[str] = Field(default_factory=list)
    local_relevance_score: float = 0.0
    relaxation_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers — value cleaning
# ---------------------------------------------------------------------------

def _stringify(val: Any) -> str:
    """Render a cell value as a plain stripped string. Returns '' for null-ish."""
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
    return s


def _row_field_texts(row: pd.Series) -> dict[str, str]:
    """Return {column: lowercased text} for each present search column."""
    out: dict[str, str] = {}
    for col in SEARCH_FIELDS:
        if col in row.index:
            text = _stringify(row[col]).lower()
            if text:
                out[col] = text
    return out


# ---------------------------------------------------------------------------
# Helpers — filtering
# ---------------------------------------------------------------------------

def _ci_eq(series: pd.Series, value: str) -> pd.Series:
    """Case-insensitive equality after stripping whitespace, NaN-safe."""
    return series.astype(str).str.strip().str.casefold() == value.strip().casefold()


def _apply_filters(
    df: pd.DataFrame,
    *,
    state: Optional[str],
    facility_type: Optional[str],
    min_trust_score: Optional[float],
) -> pd.DataFrame:
    """Apply the strict filter set. Each filter only fires when both the value
    and the corresponding column are present."""
    out = df
    if state and "state" in out.columns:
        out = out[_ci_eq(out["state"], state)]
    if facility_type and "facility_type" in out.columns:
        out = out[_ci_eq(out["facility_type"], facility_type)]
    if min_trust_score is not None and "trust_score" in out.columns:
        scores = pd.to_numeric(out["trust_score"], errors="coerce").fillna(0.0)
        out = out[scores >= float(min_trust_score)]
    return out


# ---------------------------------------------------------------------------
# Helpers — scoring
# ---------------------------------------------------------------------------

def _build_capability_plan(
    intent: AgentIntent,
) -> dict[str, list[tuple[str, float]]]:
    """
    For every capability the intent asks for, gather a list of
    (lowercased_term, weight) pairs drawn from the taxonomy.
    """
    plan: dict[str, list[tuple[str, float]]] = {}
    for cap_id in intent.capabilities_required:
        cap = CAPABILITY_INDEX.get(cap_id)
        if not cap:
            continue
        terms: list[tuple[str, float]] = []
        terms.extend((k.lower(), WEIGHT_KEYWORD) for k in cap["keywords"])
        terms.extend((s.lower(), WEIGHT_SYNONYM) for s in cap["synonyms"])
        terms.extend(
            (s.lower(), WEIGHT_STRONG_EVIDENCE)
            for s in cap["strong_evidence_keywords"]
        )
        # Deduplicate terms while keeping the largest weight per term.
        dedup: dict[str, float] = {}
        for term, weight in terms:
            if term and weight > dedup.get(term, 0.0):
                dedup[term] = weight
        plan[cap_id] = sorted(dedup.items(), key=lambda x: -x[1])
    return plan


def _score_row(
    field_texts: dict[str, str],
    capability_plan: dict[str, list[tuple[str, float]]],
    fallback_terms: list[str],
    *,
    name_text: str = "",
) -> tuple[float, list[str], list[str]]:
    """
    Return (score, matched_fields_sorted, matched_capabilities_sorted_by_input).

    A term contributes its weight once per (term, field) pair where the
    term appears under the safe-matching rules in
    :mod:`agent_core.capability_taxonomy` (word boundaries for short /
    symbol-bearing tokens, plain substring otherwise). A capability gets
    a small flat bonus when at least one of its terms matched.

    Stage 16
    --------
    1. Term presence is checked via :func:`term_matches`, not raw ``in``.
       This stops ``ER`` from matching inside ``"centers"`` or
       ``"Stapler Circumcision"`` and inflating EMERGENCY_TRAUMA scores
       for cataract / circumcision clinics.
    2. When the facility's ``name`` text contains a capability keyword
       or synonym, the row earns :data:`WEIGHT_NAME_MATCH` once per
       matched capability — pushing dialysis-named facilities above
       generic clinics for dialysis queries.
    """
    matched_fields: set[str] = set()
    matched_capabilities: list[str] = []
    score = 0.0

    if capability_plan:
        for cap_id, terms in capability_plan.items():
            cap_matched = False
            for term, weight in terms:
                for col, text in field_texts.items():
                    if term_matches(text, term):
                        matched_fields.add(col)
                        score += weight
                        cap_matched = True
            if cap_matched:
                matched_capabilities.append(cap_id)
                score += WEIGHT_CAPABILITY_BONUS
            if name_text:
                cap = CAPABILITY_INDEX.get(cap_id)
                if cap is not None:
                    name_terms = (
                        list(cap.get("keywords") or [])
                        + list(cap.get("synonyms") or [])
                    )
                    if find_matching_terms(name_text, name_terms):
                        score += WEIGHT_NAME_MATCH
                        matched_fields.add("name")
                        if cap_id not in matched_capabilities:
                            matched_capabilities.append(cap_id)
    else:
        # No required capabilities → use raw query tokens so the function
        # stays useful for free-form queries.
        for token in fallback_terms:
            for col, text in field_texts.items():
                if term_matches(text, token):
                    matched_fields.add(col)
                    score += WEIGHT_KEYWORD

    return score, sorted(matched_fields), matched_capabilities


def _fallback_terms_from_query(intent: AgentIntent) -> list[str]:
    """Tokenise the normalized query into searchable words (length >= 4)."""
    text = (intent.normalized_query or intent.original_query or intent.raw_query or "").lower()
    if not text:
        return []
    words = re.findall(r"[a-z0-9]+", text)
    # Length>=4 trims out generic noise ("the", "in", "of", "for", "and").
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if len(w) >= 4 and w not in seen:
            seen.add(w)
            out.append(w)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_local_candidates(
    df: pd.DataFrame,
    intent: AgentIntent,
    limit_pool: int = 200,
    *,
    allow_state_relaxation: bool = False,
) -> list[LocalCandidate]:
    """
    Run the local pandas-based candidate retrieval pipeline.

    Parameters
    ----------
    df:
        Facility records as a pandas DataFrame. Expected columns include
        `facility_id`, `state`, `facility_type`, `trust_score`, plus any
        of the six text columns listed in `SEARCH_FIELDS`. Missing
        columns are tolerated.
    intent:
        Parsed `AgentIntent` describing what the user asked for.
    limit_pool:
        Hard cap on the number of returned candidates. Default 200.
    allow_state_relaxation:
        Opt-in flag. When False (default) the `state` filter is **never**
        relaxed even if every other relaxation step still returned zero rows.

    Returns
    -------
    list[LocalCandidate]
        Ranked candidates (highest `local_relevance_score` first; ties
        broken by `trust_score` desc). Each candidate carries the original
        record, the fields/capabilities that matched, the score, and any
        relaxation notes describing how the strict filter was loosened.
    """
    if df is None or len(df) == 0:
        return []

    # ---- Phase 1: filter (with cascading relaxation) ------------------
    state         = intent.state
    facility_type = intent.facility_type
    min_ts        = intent.min_trust_score
    notes: list[str] = []

    filtered = _apply_filters(
        df,
        state=state,
        facility_type=facility_type,
        min_trust_score=min_ts,
    )

    if len(filtered) == 0 and min_ts is not None:
        notes.append(f"relaxed min_trust_score (was {min_ts})")
        min_ts = None
        filtered = _apply_filters(
            df, state=state, facility_type=facility_type, min_trust_score=None,
        )

    if len(filtered) == 0 and facility_type:
        notes.append(f"relaxed facility_type (was {facility_type})")
        facility_type = None
        filtered = _apply_filters(
            df, state=state, facility_type=None, min_trust_score=min_ts,
        )

    if len(filtered) == 0 and allow_state_relaxation and state:
        notes.append(f"relaxed state (was {state})")
        state = None
        filtered = _apply_filters(
            df, state=None, facility_type=facility_type, min_trust_score=min_ts,
        )

    if len(filtered) == 0:
        return []

    # ---- Phase 2: score -----------------------------------------------
    plan = _build_capability_plan(intent)
    fallback_terms = _fallback_terms_from_query(intent)

    candidates: list[LocalCandidate] = []
    for _, row in filtered.iterrows():
        field_texts = _row_field_texts(row)
        # Stage 16: feed the facility name into _score_row so dialysis-named
        # facilities outrank state-mate clinics that only loosely match.
        name_text = ""
        if "name" in row.index:
            name_text = _stringify(row["name"]).lower()
        score, matched_fields, matched_caps = _score_row(
            field_texts, plan, fallback_terms, name_text=name_text,
        )
        raw = row.to_dict()
        candidates.append(LocalCandidate(
            facility_id=str(raw.get("facility_id", "") or ""),
            raw_record=raw,
            matched_fields=matched_fields,
            matched_capabilities=matched_caps,
            local_relevance_score=score,
            relaxation_notes=list(notes),
        ))

    # ---- Phase 3: rank + truncate -------------------------------------
    def _trust(c: LocalCandidate) -> float:
        try:
            return float(c.raw_record.get("trust_score", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    candidates.sort(
        key=lambda c: (c.local_relevance_score, _trust(c)),
        reverse=True,
    )
    return candidates[:limit_pool]


# ---------------------------------------------------------------------------
# Backward-compatibility shim
# ---------------------------------------------------------------------------

def retrieve_local(query: str, df: pd.DataFrame, top_k: int = 10) -> pd.DataFrame:
    """
    Legacy single-string keyword filter on `combined_medical_evidence`.
    Retained for older call sites and tests; new code should call
    `retrieve_local_candidates()`.
    """
    if "combined_medical_evidence" not in df.columns:
        return df.head(top_k)
    if not query:
        return df.head(top_k)
    mask = df["combined_medical_evidence"].astype(str).str.contains(
        query, case=False, na=False,
    )
    return df[mask].head(top_k)
