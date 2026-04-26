"""
agent_core.demo_queries — Curated query packs for tests, demos, and CI.

Two collections live here:

* :data:`DEMO_QUERIES` — the original Stage-3 demo pack (5 queries). Kept
  intact so older tests / notebooks continue to work.

* :data:`GOLDEN_QUERIES` — 10 evaluation queries used by
  ``tests/test_golden_queries.py`` and by the static results document
  ``docs/GOLDEN_QUERY_RESULTS.md``. Each entry documents the query
  string, the intent fields the parser is expected to extract, and the
  high-level behavior the engine should produce on the canonical
  golden-query fixture DataFrame.

Each :data:`GOLDEN_QUERIES` entry is a dict with these keys:

==================== ===========================================================
``id``               Stable identifier, ``GQ-001`` … ``GQ-010``.
``query``            Raw natural-language query string.
``expected_capabilities``
                     Capability IDs the intent parser must extract. Order
                     does not matter.
``expected_state``   Indian state name, or ``None`` if the query has no
                     geographic filter.
``expected_facility_type``
                     One of ``hospital`` / ``clinic`` / ``doctor`` /
                     ``pharmacy`` / ``dentist``, or ``None``.
``expected_trust_preference``
                     One of ``trusted`` / ``verification_ok`` /
                     ``risky_allowed`` / ``unspecified``.
``expected_urgency`` One of ``emergency`` / ``urgent`` / ``routine`` /
                     ``unspecified``.
``expected_behavior``
                     Short human-readable summary of what the engine
                     should produce (recommendations vs fallback,
                     warnings, etc.).
``notes``            Free-text caveats, demo-mode commentary.
==================== ===========================================================
"""

from __future__ import annotations


DEMO_QUERIES: list[dict] = [
    {
        "id": "DQ-001",
        "query": "Find ICU facilities in Mumbai with high trust score",
        "expected_capabilities": ["ICU_CRITICAL_CARE"],
        "expected_location": "Mumbai",
    },
    {
        "id": "DQ-002",
        "query": "Which hospitals in Delhi offer dialysis and have high recommendation readiness?",
        "expected_capabilities": ["DIALYSIS_RENAL"],
        "expected_location": "Delhi",
    },
    {
        "id": "DQ-003",
        "query": "NICU facilities in Bangalore with trust_score above 0.8",
        "expected_capabilities": ["NEONATAL_PEDIATRIC"],
        "expected_location": "Bangalore",
    },
    {
        "id": "DQ-004",
        "query": "Cardiac cathlab hospitals in Chennai",
        "expected_capabilities": ["SPECIALIST_SUPPORT"],
        "expected_location": "Chennai",
    },
    {
        "id": "DQ-005",
        "query": "Trauma and emergency care centres in Hyderabad",
        "expected_capabilities": ["EMERGENCY_TRAUMA"],
        "expected_location": "Hyderabad",
    },
]


# ---------------------------------------------------------------------------
# Stage 14 — golden query evaluation suite
# ---------------------------------------------------------------------------

GOLDEN_QUERIES: list[dict] = [
    {
        "id": "GQ-001",
        "query": "Find trusted ICU facilities",
        "expected_capabilities": ["ICU_CRITICAL_CARE"],
        "expected_state": None,
        "expected_facility_type": None,
        "expected_trust_preference": "trusted",
        "expected_urgency": "unspecified",
        "expected_behavior": (
            "Returns ICU-capable facilities ranked by trust + evidence; no "
            "geographic filter; high-trust facilities should rank above "
            "low-trust ones because trust contributes to the final score."
        ),
        "notes": (
            "trust_preference is a soft hint, not a hard filter — low-trust "
            "ICU facilities still appear but rank lower."
        ),
    },
    {
        "id": "GQ-002",
        "query": "Find trusted ICU hospitals in Bihar",
        "expected_capabilities": ["ICU_CRITICAL_CARE"],
        "expected_state": "Bihar",
        "expected_facility_type": "hospital",
        "expected_trust_preference": "trusted",
        "expected_urgency": "unspecified",
        "expected_behavior": (
            "Returns Bihar hospitals with ICU evidence. State filter is "
            "respected; if no Bihar hospital exists the engine emits a "
            "fallback_message naming the unmet filters."
        ),
        "notes": "Smoke-test for the state + facility_type strict filter.",
    },
    {
        "id": "GQ-003",
        "query": "Find emergency hospitals in Maharashtra",
        "expected_capabilities": ["EMERGENCY_TRAUMA"],
        "expected_state": "Maharashtra",
        "expected_facility_type": "hospital",
        "expected_trust_preference": "unspecified",
        "expected_urgency": "emergency",
        "expected_behavior": (
            "Returns Maharashtra hospitals with emergency / trauma evidence. "
            "Emergency urgency triggers an explicit emergency next-step on "
            "every recommendation."
        ),
        "notes": "Confirms that the urgency field flows into human_next_steps.",
    },
    {
        "id": "GQ-004",
        "query": "Find dialysis centers in Uttar Pradesh",
        "expected_capabilities": ["DIALYSIS_RENAL"],
        "expected_state": "Uttar Pradesh",
        "expected_facility_type": None,
        "expected_trust_preference": "unspecified",
        "expected_urgency": "unspecified",
        "expected_behavior": (
            "Returns any UP facility with dialysis evidence. No facility_type "
            "filter — the word 'centers' is not in the parser's facility-type "
            "vocabulary."
        ),
        "notes": (
            "Multi-word state name 'Uttar Pradesh' is detected by the "
            "longest-first state matcher."
        ),
    },
    {
        "id": "GQ-005",
        "query": "Find oncology care in Gujarat",
        "expected_capabilities": ["ONCOLOGY"],
        "expected_state": "Gujarat",
        "expected_facility_type": None,
        "expected_trust_preference": "unspecified",
        "expected_urgency": "unspecified",
        "expected_behavior": (
            "Returns Gujarat facilities with oncology evidence. Free-form "
            "term 'care' does not affect intent."
        ),
        "notes": "Single-capability + single-state baseline.",
    },
    {
        "id": "GQ-006",
        "query": "Find maternity hospitals in Tamil Nadu",
        "expected_capabilities": ["MATERNAL_CARE"],
        "expected_state": "Tamil Nadu",
        "expected_facility_type": "hospital",
        "expected_trust_preference": "unspecified",
        "expected_urgency": "unspecified",
        "expected_behavior": (
            "Returns Tamil Nadu hospitals with maternity / obstetrics "
            "evidence (delivery, labour, antenatal, etc.)."
        ),
        "notes": "Multi-word state + facility_type combination.",
    },
    {
        "id": "GQ-007",
        "query": "Find neonatal ICU support in Gujarat",
        "expected_capabilities": ["NEONATAL_PEDIATRIC", "ICU_CRITICAL_CARE"],
        "expected_state": "Gujarat",
        "expected_facility_type": None,
        "expected_trust_preference": "unspecified",
        "expected_urgency": "unspecified",
        "expected_behavior": (
            "Returns Gujarat facilities with neonatal evidence; ICU keyword "
            "in the query also triggers ICU_CRITICAL_CARE on the intent."
        ),
        "notes": "Multi-capability intent — both NICU and ICU are extracted.",
    },
    {
        "id": "GQ-008",
        "query": "Find diagnostics centers in Delhi",
        "expected_capabilities": ["DIAGNOSTICS"],
        "expected_state": "Delhi",
        "expected_facility_type": None,
        "expected_trust_preference": "unspecified",
        "expected_urgency": "unspecified",
        "expected_behavior": (
            "Returns Delhi facilities with diagnostics evidence (MRI, CT, "
            "lab, etc.). 'Delhi' is both a city and a state — the intent "
            "parser sets both fields."
        ),
        "notes": (
            "Local retriever filters on the `state` column, so the state "
            "match is the operative one."
        ),
    },
    {
        "id": "GQ-009",
        "query": "Find facilities that need human verification for dialysis",
        "expected_capabilities": ["DIALYSIS_RENAL"],
        "expected_state": None,
        "expected_facility_type": None,
        "expected_trust_preference": "unspecified",
        "expected_urgency": "unspecified",
        "expected_behavior": (
            "Returns dialysis facilities; at least one returned recommendation "
            "must NOT have readiness 'Ready for recommendation' (i.e. the "
            "engine surfaces facilities that genuinely need verification)."
        ),
        "notes": (
            "Soft-filter query — the engine doesn't strictly filter by "
            "readiness. The exact phrase 'need human verification' is not in "
            "the parser's trust-preference trigger list (which requires "
            "'needs verification' / 'with verification'), so trust_preference "
            "remains 'unspecified'. The verification intent is satisfied at "
            "result time by surfacing non-ready facilities in the response."
        ),
    },
    {
        "id": "GQ-010",
        "query": "Find high-risk hospitals with unsupported emergency claims",
        "expected_capabilities": ["EMERGENCY_TRAUMA"],
        "expected_state": None,
        "expected_facility_type": "hospital",
        "expected_trust_preference": "unspecified",
        "expected_urgency": "emergency",
        "expected_behavior": (
            "Returns hospitals matching EMERGENCY_TRAUMA; at least one "
            "returned recommendation must have a missing-evidence or weak "
            "validation finding (the 'unsupported claim' angle), and a "
            "warning_flag entry must be present on that result."
        ),
        "notes": (
            "Demonstrates the validator's ability to flag facilities that "
            "claim emergency capability without any supporting equipment or "
            "procedures."
        ),
    },
]
