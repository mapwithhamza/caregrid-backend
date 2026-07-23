"""
run_agent_demo.py — Smoke-test runner for the CareGrid Vector Agent.

Loads the real 10,000-row dataset shipped at
``data/raw/caregrid_backend_export_full.csv`` and runs the full
``run_recommendation`` pipeline end-to-end against either the five
default golden queries or a single ``--query`` provided on the CLI.

Defaults are deliberately conservative:

* Tavily web verification: **disabled** (``--enable-tavily`` to opt in).
* Databricks vector search: **disabled** (``--enable-vector`` to opt in).
* ``max_results``: 5.
* Outputs: ``data/outputs/demo_agent_results.json`` +
  ``data/outputs/demo_agent_results.md``.

The script never crashes on missing optional services. Missing Tavily
key, unreachable Databricks workspace, malformed query — all degrade
gracefully and are reported in the JSON / Markdown output.

Usage examples
--------------

    # Default: 5 default queries, local-only, no Tavily, no vector.
    python run_agent_demo.py

    # Single query with live Tavily verification.
    python run_agent_demo.py \\
        --query "Find emergency hospitals in Maharashtra" \\
        --enable-tavily --web-depth basic --max-web-verified 2 --max-results 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

# Local package imports — keep at module level so failures surface early.
from agent_core.recommendation_engine import run_recommendation
from agent_core.schemas import AgentResponse
from agent_core.tavily_verifier import (
    ALLOWED_DEPTHS,
    DEPTH_BASIC,
)


# ---------------------------------------------------------------------------
# Constants — paths and required dataset schema
# ---------------------------------------------------------------------------

DEFAULT_DATASET_PATH: str = "data/raw/caregrid_backend_export_full.csv"
DEFAULT_OUTPUT_JSON:  str = "data/outputs/demo_agent_results.json"
DEFAULT_OUTPUT_MD:    str = "data/outputs/demo_agent_results.md"

REQUIRED_COLUMNS: list[str] = [
    "facility_id",
    "name",
    "facility_type",
    "city",
    "state",
    "latitude",
    "longitude",
    "trust_score",
    "trust_category",
    "recommendation_readiness",
    "combined_medical_evidence",
    "evidence_summary",
]

# The five default queries the runner exercises when ``--query`` is not given.
_DEFAULT_DEMO_QUERIES: list[str] = [
    "Find trusted ICU hospitals in Bihar",
    "Find emergency hospitals in Maharashtra",
    "Find dialysis centers in Uttar Pradesh",
    "Find oncology care in Gujarat",
    "Find maternity hospitals in Tamil Nadu",
]


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_default_demo_queries() -> list[str]:
    """Return exactly the five default golden-style demo queries.

    The list is returned by *value* — callers may safely mutate it.
    """
    return list(_DEFAULT_DEMO_QUERIES)


def load_real_dataset(path: str = DEFAULT_DATASET_PATH) -> pd.DataFrame:
    """Load the real 10k-row facility CSV.

    On a missing file this prints a clear error and ``sys.exit(2)`` —
    we deliberately don't raise, so a misconfigured machine produces a
    short, readable message instead of a Python traceback.

    Parameters
    ----------
    path:
        CSV path. Defaults to ``data/raw/caregrid_backend_export_full.csv``.

    Returns
    -------
    pandas.DataFrame
    """
    if not os.path.exists(path):
        print(f"[ERROR] Dataset not found at: {path}", file=sys.stderr)
        print(
            "Place the real export at "
            "data/raw/caregrid_backend_export_full.csv and try again.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Failed to read CSV: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)

    return df


def validate_real_dataset(df: pd.DataFrame) -> None:
    """Print a compact dataset summary and abort on missing required columns.

    Required columns are listed in :data:`REQUIRED_COLUMNS`. If any are
    absent, the function prints a clear error and ``sys.exit(2)``.
    """
    if df is None:
        print("[ERROR] Dataset is None.", file=sys.stderr)
        sys.exit(2)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]

    print("=" * 70)
    print("Dataset summary")
    print("=" * 70)
    print(f"  rows                : {len(df):,}")
    print(f"  columns             : {len(df.columns)}")

    if "state" in df.columns:
        n_states = df["state"].dropna().nunique()
        print(f"  unique states       : {n_states}")
    else:
        print("  unique states       : (state column absent)")

    if "name" in df.columns:
        sample_names = df["name"].dropna().astype(str).head(3).tolist()
        print(f"  sample facilities   : {sample_names}")
    else:
        print("  sample facilities   : (name column absent)")

    if missing:
        print()
        print(f"[ERROR] Required columns missing: {missing}", file=sys.stderr)
        print(
            "The dataset must contain every column listed in REQUIRED_COLUMNS.",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"  required columns OK : {len(REQUIRED_COLUMNS)} / {len(REQUIRED_COLUMNS)}")
    print("=" * 70)


def run_demo_queries(
    queries: list[str],
    facilities_df: pd.DataFrame,
    *,
    max_results: int = 5,
    enable_tavily: bool = False,
    enable_vector: bool = False,
    web_depth: str = DEPTH_BASIC,
    max_web_verified: int = 2,
) -> list[dict[str, Any]]:
    """Run each query through the recommendation engine and collect results.

    Returns a list of dicts (one per query) shaped as::

        {
            "query": str,
            "started_at": str (ISO 8601 UTC),
            "duration_seconds": float,
            "response": AgentResponse,            # full pipeline output
            "error": Optional[str],               # set if engine raised
        }

    The engine itself is contractually non-raising; ``error`` is here
    purely as belt-and-braces for unexpected callable replacements in tests.
    """
    if web_depth not in ALLOWED_DEPTHS:
        print(f"[WARN] Unknown --web-depth '{web_depth}', falling back to '{DEPTH_BASIC}'.")
        web_depth = DEPTH_BASIC

    results: list[dict[str, Any]] = []
    n = len(queries)
    for idx, query in enumerate(queries, start=1):
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        error_msg: Optional[str] = None
        response: Optional[AgentResponse] = None

        print()
        print(f"[{idx}/{n}] >>> {query!r}")
        try:
            response = run_recommendation(
                query=query,
                facilities_df=facilities_df,
                max_results=max_results,
                enable_vector_search=enable_vector,
                enable_web_verification=enable_tavily,
                web_verification_depth=web_depth,
                max_web_verified=max_web_verified,
            )
        except Exception as exc:  # noqa: BLE001 — engine should never raise, but defend anyway
            error_msg = f"{type(exc).__name__}: {exc}"
            print(f"      [ERROR] {error_msg}")
            traceback.print_exc(file=sys.stderr)

        duration = round(time.perf_counter() - t0, 3)

        if response is not None:
            tav = (response.trace_summary or {}).get("tavily", {}) or {}
            vec = (response.trace_summary or {}).get("vector", {}) or {}
            rs = response.retrieval_summary or {}
            print(
                f"      returned={response.returned}  "
                f"local={rs.get('local_count', 0)}  "
                f"merged={rs.get('merged_count', 0)}  "
                f"tavily_enabled={tav.get('enabled', False)}  "
                f"tavily_verified_count={tav.get('verified', 0)}  "
                f"tavily_credits={tav.get('credits_estimated', 0)}  "
                f"vector_enabled={vec.get('enabled', False)}  "
                f"vector_available={vec.get('available', False)}  "
                f"vector_count={vec.get('count', 0)}  "
                f"vector_filter_applied={vec.get('filter_applied', False)}  "
                f"({duration}s)"
            )
        results.append(
            {
                "query": query,
                "started_at": started_at,
                "duration_seconds": duration,
                "response": response,
                "error": error_msg,
            }
        )

    return results


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def _result_to_jsonable(item: dict[str, Any]) -> dict[str, Any]:
    """Render one result entry as a JSON-serialisable dict."""
    response = item.get("response")
    if response is None:
        response_payload: Any = None
    else:
        # Pydantic v2 model_dump returns plain Python types.
        response_payload = response.model_dump(mode="json")
    return {
        "query": item.get("query"),
        "started_at": item.get("started_at"),
        "duration_seconds": item.get("duration_seconds"),
        "error": item.get("error"),
        "response": response_payload,
    }


def save_json_output(results: list[dict[str, Any]], path: str = DEFAULT_OUTPUT_JSON) -> str:
    """Save a list of run results to a JSON file. Returns the path written."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result_count": len(results),
        "results": [_result_to_jsonable(r) for r in results],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    return path


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _md_escape(value: Any) -> str:
    """Render a value safely for inclusion in a Markdown table cell."""
    if value is None:
        return "—"
    s = str(value)
    return s.replace("|", "\\|").replace("\n", " ").strip() or "—"


def _format_intent(response: Optional[AgentResponse]) -> list[str]:
    """Format the interpreted intent block for the Markdown report."""
    intent = response.interpreted_intent if response is not None else None
    if intent is None and response is not None:
        intent = response.intent
    if intent is None:
        return ["- (no intent parsed)"]
    return [
        f"- **capabilities:** {', '.join(intent.capabilities_required) or '—'}",
        f"- **state:** {intent.state or '—'}",
        f"- **city:** {intent.city or '—'}",
        f"- **facility_type:** {intent.facility_type or '—'}",
        f"- **trust_preference:** {intent.trust_preference}",
        f"- **urgency:** {intent.urgency}",
    ]


def _format_retrieval_summary(response: Optional[AgentResponse]) -> list[str]:
    if response is None:
        return ["- (no response)"]
    rs = dict(response.retrieval_summary or {})
    lines = [
        f"- **local_count:** {rs.get('local_count', 0)}",
        f"- **vector_enabled:** {rs.get('vector_enabled', False)}",
        f"- **vector_available:** {rs.get('vector_available', False)}",
        f"- **vector_count:** {rs.get('vector_count', 0)}",
        f"- **vector_reason:** `{rs.get('vector_reason', '') or '—'}`",
        f"- **vector_filter_applied:** {rs.get('vector_filter_applied', False)}",
        f"- **vector_endpoint:** `{rs.get('vector_endpoint', '') or '—'}`",
        f"- **vector_index:** `{rs.get('vector_index', '') or '—'}`",
        f"- **merged_count:** {rs.get('merged_count', 0)}",
        f"- **after_top_k_count:** {rs.get('after_top_k_count', 0)}",
        f"- **relaxation_used:** {rs.get('relaxation_used', False)}",
        f"- **returned:** {response.returned}",
    ]
    # Stage 18: also surface the Tavily summary keys here so a single
    # block tells the operator what each retrieval arm produced.
    if "web_verification_enabled" in rs or "tavily_verified_count" in rs:
        lines.extend([
            f"- **web_verification_enabled:** {rs.get('web_verification_enabled', False)}",
            f"- **tavily_verified_count:** {rs.get('tavily_verified_count', 0)}",
            f"- **tavily_depth:** `{rs.get('tavily_depth', '—') or '—'}`",
            f"- **tavily_credits_estimated:** {rs.get('tavily_credits_estimated', 0)}",
        ])
    return lines


def _format_top_recommendations_table(response: Optional[AgentResponse]) -> list[str]:
    if response is None or not response.recommendations:
        return ["_(no recommendations)_"]
    header = (
        "| rank | name | city | state | facility_type | trust_score | "
        "trust_category | recommendation_readiness | final_score |"
    )
    sep = "| --- " * 9 + "|"
    lines = [header, sep]
    for i, rec in enumerate(response.recommendations, start=1):
        score = (
            rec.score_breakdown.final_score
            if rec.score_breakdown is not None
            else 0.0
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(i),
                    _md_escape(rec.name or rec.facility_id),
                    _md_escape(rec.city),
                    _md_escape(rec.state),
                    _md_escape(rec.facility_type),
                    f"{rec.trust_score:.3f}",
                    _md_escape(rec.trust_category),
                    _md_escape(rec.recommendation_readiness),
                    f"{score:.3f}",
                ]
            )
            + " |"
        )
    return lines


def _format_evidence_section(response: Optional[AgentResponse]) -> list[str]:
    if response is None or not response.recommendations:
        return ["_(no evidence)_"]
    blocks: list[str] = []
    for i, rec in enumerate(response.recommendations, start=1):
        if not rec.evidence_snippets:
            blocks.append(f"**{i}. {rec.name or rec.facility_id}** — _(no snippets)_")
            continue
        blocks.append(f"**{i}. {rec.name or rec.facility_id}**")
        for snip in rec.evidence_snippets[:5]:
            cap = snip.capability_id or "—"
            level = snip.support_level or "weak"
            field = snip.source_field or "—"
            blocks.append(
                f"- `{cap}` / `{level}` / `{field}` — {_md_escape(snip.excerpt)}"
            )
    return blocks


def _format_findings_section(response: Optional[AgentResponse]) -> list[str]:
    if response is None or not response.recommendations:
        return ["_(no findings)_"]
    blocks: list[str] = []
    for i, rec in enumerate(response.recommendations, start=1):
        if not rec.validation_findings:
            blocks.append(
                f"**{i}. {rec.name or rec.facility_id}** — _(no findings)_"
            )
            continue
        blocks.append(f"**{i}. {rec.name or rec.facility_id}**")
        for f in rec.validation_findings:
            cap = f.capability or "—"
            blocks.append(
                f"- `{f.finding_type or f.rule}` / `{f.severity}` / `{cap}` — "
                f"impact={f.recommendation_impact} — {_md_escape(f.message)}"
            )
    return blocks


def _format_warning_flags_section(response: Optional[AgentResponse]) -> list[str]:
    if response is None or not response.recommendations:
        return ["_(no warnings)_"]
    blocks: list[str] = []
    for i, rec in enumerate(response.recommendations, start=1):
        flags = list(rec.warning_flags or rec.warnings or [])
        if not flags:
            blocks.append(f"**{i}. {rec.name or rec.facility_id}** — _(none)_")
            continue
        blocks.append(
            f"**{i}. {rec.name or rec.facility_id}** — "
            + ", ".join(f"`{x}`" for x in flags)
        )
    return blocks


def _format_vector_section(response: Optional[AgentResponse]) -> list[str]:
    """Render the Stage-17 Databricks Vector Search section."""
    if response is None:
        return ["_(no response)_"]
    vec = (response.trace_summary or {}).get("vector", {}) or {}
    rs = dict(response.retrieval_summary or {})
    enabled = bool(vec.get("enabled"))
    blocks: list[str] = [
        f"- **enabled:** {enabled}",
        f"- **available:** {vec.get('available', False)}",
        f"- **count:** {vec.get('count', rs.get('vector_count', 0))}",
        f"- **reason:** `{vec.get('reason', '') or '—'}`",
        f"- **filter_applied:** {vec.get('filter_applied', False)}",
        f"- **filters_requested:** "
        f"`{vec.get('filters_requested') or rs.get('vector_filters_requested') or '—'}`",
        f"- **endpoint:** `{vec.get('endpoint', '') or rs.get('vector_endpoint', '') or '—'}`",
        f"- **index:** `{vec.get('index', '') or rs.get('vector_index', '') or '—'}`",
    ]
    if not enabled:
        blocks.append(
            "- _Vector search disabled — pass `--enable-vector` and configure "
            "Databricks credentials in `.env` to invoke real vector search._"
        )
        return blocks

    rec_blocks: list[str] = []
    for i, rec in enumerate(response.recommendations, start=1):
        sb = rec.score_breakdown
        vec_comp = sb.vector_similarity_component if sb is not None else 0.0
        rec_blocks.append(
            f"  - **{i}. {rec.name or rec.facility_id}** — "
            f"`vector_similarity_component={vec_comp:.4f}`"
        )
    if rec_blocks:
        blocks.append("")
        blocks.extend(rec_blocks)
    return blocks


def _format_tavily_section(response: Optional[AgentResponse]) -> list[str]:
    if response is None:
        return ["_(no response)_"]
    tav = (response.trace_summary or {}).get("tavily", {}) or {}
    enabled = bool(tav.get("enabled"))
    blocks: list[str] = [
        f"- **enabled:** {enabled}",
        f"- **verified count:** {tav.get('verified', 0)}",
        f"- **credits estimated:** {tav.get('credits_estimated', 0)}",
        f"- **depth:** {tav.get('depth', '—')}",
    ]
    if not enabled:
        blocks.append(
            "- _Tavily disabled — pass `--enable-tavily` to invoke real web verification._"
        )
        return blocks

    rec_blocks: list[str] = []
    for i, rec in enumerate(response.recommendations, start=1):
        web = rec.web_verification
        if web is None:
            rec_blocks.append(
                f"  - **{i}. {rec.name or rec.facility_id}** — _(not verified)_"
            )
            continue
        rec_blocks.append(
            f"  - **{i}. {rec.name or rec.facility_id}** — "
            f"`web_checked={web.web_checked}` "
            f"`web_available={web.web_available}` "
            f"`status={web.verification_status}` "
            f"`score={web.verification_score:.2f}`"
        )
        if web.top_url:
            rec_blocks.append(f"    - top_url: {web.top_url}")
        if web.top_snippet:
            rec_blocks.append(f"    - top_snippet: {_md_escape(web.top_snippet)}")
        if web.error_message:
            rec_blocks.append(f"    - error: {_md_escape(web.error_message)}")
    if rec_blocks:
        blocks.append("")
        blocks.extend(rec_blocks)
    return blocks


def _format_score_breakdown_section(response: Optional[AgentResponse]) -> list[str]:
    """Stage-18: per-recommendation table of every score component.

    Lets a judge confirm at a glance that vector and Tavily contributions
    are non-zero where expected and that penalties are applied where the
    validator flagged something.
    """
    if response is None or not response.recommendations:
        return ["_(no recommendations)_"]
    header = (
        "| rank | name | trust | readiness | capability+local | evidence | "
        "vector | tavily | val_pen | warn_pen | final |"
    )
    sep = "| --- " * 11 + "|"
    lines = [header, sep]
    for i, rec in enumerate(response.recommendations, start=1):
        sb = rec.score_breakdown
        if sb is None:
            lines.append(
                f"| {i} | {_md_escape(rec.name or rec.facility_id)} "
                f"| — | — | — | — | — | — | — | — | — |"
            )
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(i),
                    _md_escape(rec.name or rec.facility_id),
                    f"{sb.trust_score_component:.4f}",
                    f"{sb.readiness_component:.4f}",
                    f"{sb.capability_match_component:.4f}",
                    f"{sb.evidence_strength_component:.4f}",
                    f"{sb.vector_similarity_component:.4f}",
                    f"{sb.tavily_verification_component:.4f}",
                    f"{sb.validation_penalty:.4f}",
                    f"{sb.warning_penalty:.4f}",
                    f"{sb.final_score:.4f}",
                ]
            )
            + " |"
        )
    return lines


def _format_human_next_steps_section(response: Optional[AgentResponse]) -> list[str]:
    """Stage-18: surface the per-recommendation ``human_next_steps`` so a
    reviewer knows what a clinician should do before acting on a result."""
    if response is None or not response.recommendations:
        return ["_(no recommendations)_"]
    blocks: list[str] = []
    for i, rec in enumerate(response.recommendations, start=1):
        steps = list(rec.human_next_steps or [])
        if rec.reason_for_recommendation:
            blocks.append(
                f"**{i}. {rec.name or rec.facility_id}** — "
                f"_{_md_escape(rec.reason_for_recommendation)}_"
            )
        else:
            blocks.append(f"**{i}. {rec.name or rec.facility_id}**")
        if not steps:
            blocks.append("- _(no specific next steps)_")
            continue
        for step in steps:
            blocks.append(f"- {_md_escape(step)}")
    return blocks


def _format_trace_summary_section(response: Optional[AgentResponse]) -> list[str]:
    """Stage-18: render the ``trace_summary`` (stages, vector, tavily,
    errors) as a fenced JSON block so a reviewer can audit the run.

    We deliberately print the audit log as a trimmed counter only — the
    full event list is in the JSON output for anyone who needs it.
    """
    if response is None:
        return ["_(no response)_"]
    ts = dict(response.trace_summary or {})

    stages = ts.get("stages") or []
    errors = ts.get("errors") or []
    vector = ts.get("vector") or {}
    tavily = ts.get("tavily") or {}

    audit = ts.get("audit_log") or {}
    audit_event_types = list(audit.get("event_types") or [])

    summary = {
        "stages":  [s.get("stage") for s in stages if isinstance(s, dict)],
        "errors":  errors,
        "vector":  vector,
        "tavily":  tavily,
        "audit_event_types": audit_event_types,
    }
    return [
        "```json",
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        "```",
    ]


def _format_safety_note(response: Optional[AgentResponse]) -> list[str]:
    if response is None:
        return ["_(no response)_"]
    return ["> " + (response.safety_note or "(no safety note)")]


def save_markdown_report(
    results: list[dict[str, Any]],
    path: str = DEFAULT_OUTPUT_MD,
) -> str:
    """Save a human-readable Markdown report. Returns the path written."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    out: list[str] = []
    out.append("# CareGrid Vector Agent — Demo Run Report")
    out.append("")
    out.append(f"_Generated at {datetime.now(timezone.utc).isoformat()}_")
    out.append("")
    out.append(f"**Queries run:** {len(results)}")
    out.append("")
    out.append("---")
    out.append("")

    for idx, item in enumerate(results, start=1):
        query = item.get("query") or "(blank)"
        response = item.get("response")
        duration = item.get("duration_seconds")
        error = item.get("error")

        out.append(f"# Query {idx}: {query}")
        out.append("")
        if duration is not None:
            out.append(f"_Duration: {duration}s_")
            out.append("")
        if error:
            out.append(f"**ERROR:** `{_md_escape(error)}`")
            out.append("")

        out.append("## Interpreted Intent")
        out.extend(_format_intent(response))
        out.append("")

        out.append("## Retrieval Summary")
        out.extend(_format_retrieval_summary(response))
        out.append("")

        out.append("## Top Recommendations")
        out.extend(_format_top_recommendations_table(response))
        out.append("")

        out.append("## Score Breakdown")
        out.extend(_format_score_breakdown_section(response))
        out.append("")

        out.append("## Evidence Snippets")
        out.extend(_format_evidence_section(response))
        out.append("")

        out.append("## Validation Findings")
        out.extend(_format_findings_section(response))
        out.append("")

        out.append("## Warning Flags")
        out.extend(_format_warning_flags_section(response))
        out.append("")

        out.append("## Vector Search")
        out.extend(_format_vector_section(response))
        out.append("")

        out.append("## Tavily Verification")
        out.extend(_format_tavily_section(response))
        out.append("")

        out.append("## Human Next Steps")
        out.extend(_format_human_next_steps_section(response))
        out.append("")

        out.append("## Safety Note")
        out.extend(_format_safety_note(response))
        out.append("")

        out.append("## Debug / Trace Summary")
        out.extend(_format_trace_summary_section(response))
        out.append("")

        out.append("---")
        out.append("")

    Path(path).write_text("\n".join(out), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_agent_demo.py",
        description=(
            "Run the CareGrid Vector Agent against the real 10k-row dataset. "
            "Tavily and Databricks vector search are disabled by default."
        ),
    )
    p.add_argument(
        "--query", default=None,
        help="Run a single custom query instead of the 5 defaults.",
    )
    p.add_argument(
        "--max-results", type=int, default=5,
        help="Top-N recommendations per query (default: 5).",
    )
    p.add_argument(
        "--enable-tavily", action="store_true",
        help="Enable real Tavily web verification of top recommendations.",
    )
    p.add_argument(
        "--enable-vector", action="store_true",
        help="Enable Databricks vector search (must be configured in .env).",
    )
    p.add_argument(
        "--web-depth", default=DEPTH_BASIC, choices=sorted(ALLOWED_DEPTHS),
        help="Tavily search depth (default: basic).",
    )
    p.add_argument(
        "--max-web-verified", type=int, default=2,
        help="Max top recommendations to verify via Tavily (default: 2).",
    )
    p.add_argument(
        "--dataset-path", default=DEFAULT_DATASET_PATH,
        help=f"Override dataset CSV path (default: {DEFAULT_DATASET_PATH}).",
    )
    p.add_argument(
        "--output-json", default=DEFAULT_OUTPUT_JSON,
        help=f"JSON output path (default: {DEFAULT_OUTPUT_JSON}).",
    )
    p.add_argument(
        "--output-md", default=DEFAULT_OUTPUT_MD,
        help=f"Markdown output path (default: {DEFAULT_OUTPUT_MD}).",
    )
    return p


def _print_run_banner(args: argparse.Namespace) -> None:
    print("=" * 70)
    print("CareGrid Vector Agent — Demo Runner")
    print("=" * 70)
    print(f"  dataset            : {args.dataset_path}")
    print(f"  enable_tavily      : {args.enable_tavily}")
    print(f"  enable_vector      : {args.enable_vector}")
    print(f"  web_depth          : {args.web_depth}")
    print(f"  max_results        : {args.max_results}")
    print(f"  max_web_verified   : {args.max_web_verified}")
    print(f"  output (JSON)      : {args.output_json}")
    print(f"  output (Markdown)  : {args.output_md}")

    # Surface Tavily key presence (without leaking the value).
    key_present = bool(os.environ.get("TAVILY_API_KEY") or "").__bool__()
    if args.enable_tavily:
        if key_present:
            print("  TAVILY_API_KEY     : present (real call expected)")
        else:
            print("  TAVILY_API_KEY     : MISSING — verifications will be 'skipped'")

    # Surface Databricks credentials presence. We read these via the
    # Settings object so .env values (loaded by pydantic-settings) are
    # visible — os.environ alone is misleading here.
    if args.enable_vector:
        try:
            from config.settings import settings as _runtime_settings  # local import
            host  = _runtime_settings.databricks_host or ""
            token = _runtime_settings.databricks_token or ""
            endpoint = _runtime_settings.vector_search_endpoint or ""
            index    = _runtime_settings.vector_search_index    or ""
        except Exception:  # noqa: BLE001
            host = endpoint = index = ""
            token = ""
        token_present = bool(token and not token.startswith("<"))
        print(f"  DATABRICKS_HOST    : {host or '(unset)'}")
        print(f"  DATABRICKS_TOKEN   : {'present' if token_present else 'MISSING / placeholder'}")
        print(f"  VECTOR_ENDPOINT    : {endpoint or '(unset)'}")
        print(f"  VECTOR_INDEX       : {index or '(unset)'}")
    print("=" * 70)


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    _print_run_banner(args)

    df = load_real_dataset(args.dataset_path)
    validate_real_dataset(df)

    queries = [args.query] if args.query else get_default_demo_queries()
    print()
    print(f"Running {len(queries)} query/queries …")

    results = run_demo_queries(
        queries,
        df,
        max_results=args.max_results,
        enable_tavily=args.enable_tavily,
        enable_vector=args.enable_vector,
        web_depth=args.web_depth,
        max_web_verified=args.max_web_verified,
    )

    json_path = save_json_output(results, args.output_json)
    md_path   = save_markdown_report(results, args.output_md)

    print()
    print("=" * 70)
    print("Outputs")
    print("=" * 70)
    print(f"  JSON     : {json_path}")
    print(f"  Markdown : {md_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
