"""
agent_core.contradiction_rules — Detect inconsistencies inside a single
facility record before it is recommended.

A *contradiction* is a logical conflict between two or more fields on the
same record (e.g. a high `trust_score` paired with a `trust_category` of
`High Risk / Insufficient Evidence`). These never come from external
sources — they are deterministic checks applied to the record's own data.

Every rule defines:
  * `id`         — short stable identifier (used in audit logs and tests)
  * `description`— human-readable description
  * `severity`   — `info` | `low` | `medium` | `high`
  * `check`      — `Callable[[dict], bool]`  (must NEVER raise)

`check_contradictions(record)` returns the list of triggered rule IDs
(kept for backward compatibility). `find_contradictions(record)` returns
the richer dicts that the validator turns into `ValidationFinding`s.
"""

from __future__ import annotations

from typing import Any, Callable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    """Coerce any value to float, returning `default` when impossible."""
    try:
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _norm(val: Any) -> str:
    """Render a string-like field as a stripped string for comparison."""
    return ("" if val is None else str(val)).strip()


def _is_blank(val: Any) -> bool:
    """True when ``val`` is null-ish or contains no real content.

    Stage 16 helper: used by
    :data:`CR_HIGH_ACUITY_CLAIM_NO_EVIDENCE` to decide whether an
    emergency/ICU/dialysis claim has any concrete equipment or
    procedure backing it.
    """
    s = _norm(val).lower()
    if not s:
        return True
    return s in {"none", "nan", "null", "n/a", "na", "<na>", "nat", "[]", "''", '""'}


_HIGH_ACUITY_CLAIM_TERMS = (
    "emergency", "trauma", "casualty", "icu", "intensive care",
    "critical care", "dialysis",
)


def _claims_high_acuity(record: dict) -> bool:
    """True when ``specialties`` or ``capabilities_raw`` mention an
    emergency / trauma / ICU / dialysis claim.

    The scan is plain substring after lowercasing — the claim itself is
    enough to flag; whether the claim is *backed* by equipment is the
    job of the contradiction rule that calls this helper.
    """
    text = (
        _norm(record.get("specialties")) + " | " +
        _norm(record.get("capabilities_raw"))
    ).lower()
    return any(t in text for t in _HIGH_ACUITY_CLAIM_TERMS)


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------
# Trust categories from `config.settings.TRUST_CATEGORIES`:
#   "High Trust / Evidence Supported"
#   "Moderate Trust / Verify Before Use"
#   "Low Trust / Needs Human Verification"
#   "High Risk / Insufficient Evidence"
#
# Recommendation readiness from `config.settings.RECOMMENDATION_READINESS_VALUES`:
#   "Ready for recommendation"
#   "Usable with verification"
#   "Do not recommend without human review"
# ---------------------------------------------------------------------------

CONTRADICTION_RULES: list[dict[str, Any]] = [
    {
        "id": "CR_HIGH_SCORE_LOW_TRUST_CATEGORY",
        "description": (
            "trust_score is >= 0.8 but trust_category is 'Low Trust / "
            "Needs Human Verification' or 'High Risk / Insufficient Evidence'."
        ),
        "severity": "high",
        "check": (lambda r:
            _safe_float(r.get("trust_score")) >= 0.8
            and _norm(r.get("trust_category")) in {
                "Low Trust / Needs Human Verification",
                "High Risk / Insufficient Evidence",
            }
        ),
    },
    {
        "id": "CR_LOW_SCORE_HIGH_TRUST_CATEGORY",
        "description": (
            "trust_score is < 0.4 but trust_category is "
            "'High Trust / Evidence Supported'."
        ),
        "severity": "high",
        "check": (lambda r:
            _safe_float(r.get("trust_score"), default=1.0) < 0.4
            and _norm(r.get("trust_category")) == "High Trust / Evidence Supported"
        ),
    },
    {
        "id": "CR_READY_BUT_LOW_SCORE",
        "description": (
            "recommendation_readiness is 'Ready for recommendation' but "
            "trust_score is < 0.4."
        ),
        "severity": "high",
        "check": (lambda r:
            _norm(r.get("recommendation_readiness")) == "Ready for recommendation"
            and _safe_float(r.get("trust_score"), default=1.0) < 0.4
        ),
    },
    {
        "id": "CR_DO_NOT_RECOMMEND_BUT_HIGH_SCORE",
        "description": (
            "recommendation_readiness is 'Do not recommend without human review' "
            "but trust_score is >= 0.9."
        ),
        "severity": "medium",
        "check": (lambda r:
            _norm(r.get("recommendation_readiness")) == "Do not recommend without human review"
            and _safe_float(r.get("trust_score")) >= 0.9
        ),
    },
    {
        # Stage 16: catches "Sketchy Emergency Hospital"-style records
        # that claim an emergency/ICU/dialysis specialty but have NO
        # equipment and NO procedures listed. Without this rule the
        # validator would mark the claim as "supported" because the
        # capabilities_raw text alone hits the strong term list.
        "id": "CR_HIGH_ACUITY_CLAIM_NO_EVIDENCE",
        "description": (
            "Facility claims a high-acuity capability (emergency, "
            "trauma, ICU, dialysis, or critical care) in specialties / "
            "capabilities_raw, but has empty equipment AND empty "
            "procedures — the claim is unverifiable."
        ),
        "severity": "high",
        "check": (lambda r: (
            _claims_high_acuity(r)
            and _is_blank(r.get("equipment"))
            and _is_blank(r.get("procedures"))
        )),
    },
    {
        "id": "CR_MISSING_TRUST_CATEGORY",
        "description": (
            "trust_score is set (>0) but trust_category is empty — the "
            "agent cannot interpret the score without a category."
        ),
        "severity": "low",
        "check": (lambda r:
            _safe_float(r.get("trust_score")) > 0.0
            and _norm(r.get("trust_category")) == ""
        ),
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_contradictions(record: dict) -> list[dict]:
    """
    Run every rule against `record` and return the dicts of those that
    triggered. Each returned dict mirrors the rule definition (id,
    description, severity).

    Never raises — a faulty rule callable is silently skipped.
    """
    if not record:
        return []
    out: list[dict] = []
    for rule in CONTRADICTION_RULES:
        try:
            if rule["check"](record):
                out.append({
                    "id": rule["id"],
                    "description": rule["description"],
                    "severity": rule.get("severity", "low"),
                })
        except Exception:
            continue
    return out


def check_contradictions(record: dict) -> list[str]:
    """Backward-compatible: returns just the IDs of triggered rules."""
    return [r["id"] for r in find_contradictions(record)]


def get_rule(rule_id: str) -> dict | None:
    """Lookup a rule definition by id (or `None` if no such rule)."""
    for rule in CONTRADICTION_RULES:
        if rule["id"] == rule_id:
            return rule
    return None
