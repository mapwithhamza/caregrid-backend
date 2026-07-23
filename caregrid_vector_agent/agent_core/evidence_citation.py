"""
agent_core.evidence_citation — Extract supporting evidence snippets per capability.

For every capability the user asked about, this module scans a facility record
across six text fields, splits the text into sentence-like segments, and pulls
out the segments that mention the capability's keywords or strong-evidence
terms. Each surviving segment becomes an `EvidenceSnippet` with a
`support_level` that summarises how strong the evidence is.

The strength rules:
  * A `strong_evidence_keyword` (e.g. "ventilator", "linear accelerator") in
    **any** field → `strong`
  * A capability `keyword` / `synonym` / supporting-equipment term in
    `equipment` or `procedures` → `strong`  (concrete clinical content)
  * Same kind of term in `specialties` or `capabilities_raw` → `moderate`
  * Same kind of term in `evidence_summary` or `combined_medical_evidence`
    only → `weak`

`contradiction` is the fourth allowed `support_level` value but is never
emitted from this module — it is reserved for `contradiction_rules.py`.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from agent_core.capability_taxonomy import (
    CAPABILITY_INDEX,
    find_matching_terms,
)
from agent_core.schemas import EvidenceSnippet


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Allowed support_level values. Stable strings — safe to assert against.
SUPPORT_STRONG        = "strong"
SUPPORT_MODERATE      = "moderate"
SUPPORT_WEAK          = "weak"
SUPPORT_CONTRADICTION = "contradiction"
EVIDENCE_SUPPORT_LEVELS: list[str] = [
    SUPPORT_STRONG,
    SUPPORT_MODERATE,
    SUPPORT_WEAK,
    SUPPORT_CONTRADICTION,
]

# Fields searched, in priority order (most concrete first). The list order
# is also used as a tiebreaker when ranking snippets.
EVIDENCE_FIELDS_PRIORITY: list[str] = [
    "equipment",
    "procedures",
    "specialties",
    "capabilities_raw",
    "evidence_summary",
    "combined_medical_evidence",
]

# Field-based promotion buckets. A regular keyword landing in any of these
# fields is promoted to the corresponding support level.
_STRONG_FIELDS   = {"equipment", "procedures"}
_MODERATE_FIELDS = {"specialties", "capabilities_raw"}
# Anything else falls through to `weak`.

MAX_SNIPPETS_PER_CAPABILITY = 3
MAX_EXCERPT_LENGTH          = 240

# Numeric scores per support level — convenient for ranking/recommendation use.
_LEVEL_SCORE: dict[str, float] = {
    SUPPORT_STRONG:   1.0,
    SUPPORT_MODERATE: 0.6,
    SUPPORT_WEAK:     0.3,
}
_LEVEL_RANK: dict[str, int] = {
    SUPPORT_STRONG:   0,
    SUPPORT_MODERATE: 1,
    SUPPORT_WEAK:     2,
}

# Sentence/segment splitter. Splits on `.`, `;`, newline, and pipe — these
# are the separators used by `evidence_builder.build_combined_evidence()`
# (newlines) and `vector_source_builder.build_vector_text()` (pipes). We
# intentionally do NOT split on `-` so terms like "C-arm" or "T-cell" survive.
_SEGMENT_SPLIT_RE = re.compile(r"[.;\n|]+")

_NULLISH_TOKENS = {"", "none", "nan", "null", "n/a", "na", "<na>", "nat"}


# ---------------------------------------------------------------------------
# Helpers
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
        # Unwrap python-list-looking strings: "['ICU','Dialysis']" → "ICU, Dialysis"
        inner = s[1:-1].replace("'", "").replace('"', "")
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        return ", ".join(parts)
    return s


def _split_segments(text: str) -> list[str]:
    """Split a text blob into sentence-like segments and trim whitespace."""
    if not text:
        return []
    parts = _SEGMENT_SPLIT_RE.split(text)
    out: list[str] = []
    for p in parts:
        cleaned = " ".join(p.split())
        if cleaned:
            out.append(cleaned)
    return out


def _truncate(s: str, max_len: int = MAX_EXCERPT_LENGTH) -> str:
    """Concise excerpt with whole-word truncation and an ellipsis suffix."""
    s = " ".join(s.split())
    if len(s) <= max_len:
        return s
    cut = s.rfind(" ", 0, max_len - 3)
    if cut < max_len // 2:
        cut = max_len - 3
    return s[:cut].rstrip() + "..."


def _capability_terms(capability_id: str) -> tuple[list[str], list[str]]:
    """
    Return (strong_terms, regular_terms) for a capability, lowercased and
    de-duplicated. Longer terms come first so the longest match wins
    (e.g. "intensive care unit" before "intensive care").
    """
    cap = CAPABILITY_INDEX.get(capability_id)
    if not cap:
        return [], []

    strong = {t.lower().strip() for t in cap["strong_evidence_keywords"] if t}
    regular = {
        t.lower().strip()
        for t in (cap["keywords"] + cap["synonyms"] + cap["supporting_equipment"])
        if t
    }
    # A term that is "strong" must not also be matched as "regular" — that
    # would inflate matched_terms and double-count the same hit.
    regular -= strong

    return (
        sorted(strong, key=len, reverse=True),
        sorted(regular, key=len, reverse=True),
    )


def _find_terms(segment_lower: str, terms: list[str]) -> list[str]:
    """
    Return the (lowercased) terms from ``terms`` that occur in
    ``segment_lower`` under the safe-matching rules in
    :mod:`agent_core.capability_taxonomy`.

    Stage 16: replaces the previous raw ``in`` substring scan, which
    leaked false positives such as ``ER`` matching inside ``"Stapler
    Circumcision"`` or ``"cataract surgery"`` and promoting
    non-emergency facilities as emergency-care evidence.

    The output preserves the longest-first ordering returned by
    :func:`find_matching_terms` so callers that pick element ``[0]``
    get the most specific clinical hit.
    """
    if not segment_lower or not terms:
        return []
    return find_matching_terms(segment_lower, terms)


def _classify(field: str, has_strong_term: bool) -> str:
    """Pick the support level given the source field and whether a strong
    term was matched."""
    if has_strong_term:
        return SUPPORT_STRONG
    if field in _STRONG_FIELDS:
        return SUPPORT_STRONG
    if field in _MODERATE_FIELDS:
        return SUPPORT_MODERATE
    return SUPPORT_WEAK


# ---------------------------------------------------------------------------
# Public API — extraction
# ---------------------------------------------------------------------------

def extract_evidence_snippets(
    record: dict,
    requested_capabilities: list[str],
) -> list[EvidenceSnippet]:
    """
    Pull the best evidence segments out of `record` for each requested capability.

    Behaviour
    ---------
    * Six text fields are scanned in priority order:
      `equipment` → `procedures` → `specialties` → `capabilities_raw` →
      `evidence_summary` → `combined_medical_evidence`.
    * Each field's text is split into sentence-like segments.
    * A segment qualifies if it contains at least one capability keyword,
      synonym, supporting-equipment term, or strong-evidence keyword.
    * Each kept segment is stamped with a `support_level` per the rules
      in the module docstring.
    * At most `MAX_SNIPPETS_PER_CAPABILITY` (=3) snippets are kept per
      capability, ranked by support level (strong → moderate → weak) with
      field priority as the tiebreaker. Duplicate excerpts are de-duped.
    * If `requested_capabilities` is empty or no segment matches, returns `[]`.

    Parameters
    ----------
    record:
        A facility record as a dict (typically a pandas Series converted via
        `.to_dict()` or a `FacilityRecord.model_dump()`). Must contain
        `facility_id`. Missing or null text fields are tolerated.
    requested_capabilities:
        A list of capability IDs (e.g. `["ICU_CRITICAL_CARE", "OXYGEN_SUPPORT"]`).
        Unknown IDs are silently ignored.

    Returns
    -------
    list[EvidenceSnippet]
        Snippets across all requested capabilities, in capability order
        (preserving the input order) and ranked within each capability.
    """
    if not record or not requested_capabilities:
        return []

    facility_id = str(record.get("facility_id", "") or "")
    out: list[EvidenceSnippet] = []

    # Precompute cleaned per-field segments once per record.
    field_segments: dict[str, list[str]] = {}
    for field in EVIDENCE_FIELDS_PRIORITY:
        text = _stringify(record.get(field))
        field_segments[field] = _split_segments(text) if text else []

    for cap_id in requested_capabilities:
        strong_terms, regular_terms = _capability_terms(cap_id)
        if not strong_terms and not regular_terms:
            continue

        # candidates: list of (level_rank, field_rank, snippet)
        candidates: list[tuple[int, int, EvidenceSnippet]] = []

        for field in EVIDENCE_FIELDS_PRIORITY:
            field_rank = EVIDENCE_FIELDS_PRIORITY.index(field)
            for segment in field_segments[field]:
                seg_lower = segment.lower()
                strong_hits  = _find_terms(seg_lower, strong_terms)
                regular_hits = _find_terms(seg_lower, regular_terms)
                if not strong_hits and not regular_hits:
                    continue

                level = _classify(field, has_strong_term=bool(strong_hits))
                snippet = EvidenceSnippet(
                    facility_id=facility_id,
                    excerpt=_truncate(segment),
                    source_field=field,
                    relevance_score=_LEVEL_SCORE[level],
                    support_level=level,
                    capability_id=cap_id,
                    matched_terms=sorted(set(strong_hits + regular_hits)),
                )
                candidates.append((_LEVEL_RANK[level], field_rank, snippet))

        # Rank by (level desc via rank asc, field priority asc) then dedupe by excerpt.
        candidates.sort(key=lambda x: (x[0], x[1]))

        seen: set[str] = set()
        kept: list[EvidenceSnippet] = []
        for _, _, snippet in candidates:
            key = snippet.excerpt.lower()
            if key in seen:
                continue
            seen.add(key)
            kept.append(snippet)
            if len(kept) >= MAX_SNIPPETS_PER_CAPABILITY:
                break
        out.extend(kept)

    return out


# ---------------------------------------------------------------------------
# Backward-compatibility — citation formatter
# ---------------------------------------------------------------------------

def format_citations(blocks: list[EvidenceSnippet]) -> str:
    """Render a list of snippets as a numbered citation list."""
    lines: list[str] = []
    for i, block in enumerate(blocks, 1):
        lines.append(f"[{i}] facility_id={block.facility_id}: {block.excerpt[:200]}")
    return "\n".join(lines)
