"""
CareGrid Gemini LLM helper.

Uses the official google-genai SDK (google.genai) to call Gemini 1.5 Flash
and generate an AI summary of the top rule-based facility recommendations.

All fields returned map to optional AI fields in AgentRecommendResponse
which the frontend AI Summary panel already renders.

Gracefully returns None for all AI fields if:
- GEMINI_API_KEY is not set
- google-genai is not installed
- The API call fails for any reason
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy-import so the app still boots if the package is not installed.
try:
    from google import genai  # type: ignore[import]
    from google.genai import types as genai_types  # type: ignore[import]
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False


def _load_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def _build_prompt(query: str, recommendations: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, r in enumerate(recommendations[:5], start=1):
        name = r.get("name") or "Unknown"
        ftype = r.get("facility_type") or "N/A"
        city = r.get("city") or "N/A"
        state = r.get("state") or "N/A"
        trust_score = r.get("trust_score")
        trust_score_str = f"{trust_score:.1f}" if isinstance(trust_score, (int, float)) else "N/A"
        trust_cat = r.get("trust_category") or "N/A"
        readiness = r.get("recommendation_readiness") or "N/A"
        capabilities = ", ".join(r.get("matched_capabilities") or []) or "general match"
        warnings = "; ".join(r.get("warning_flags") or []) or "none"
        evidence = (r.get("evidence_summary") or "")[:200]

        lines.append(
            f"{i}. {name} ({ftype}) -- {city}, {state}\n"
            f"   Trust Score: {trust_score_str} | Category: {trust_cat}\n"
            f"   Readiness: {readiness}\n"
            f"   Matched capabilities: {capabilities}\n"
            f"   Warnings: {warnings}\n"
            f"   Evidence snippet: {evidence}"
        )

    facility_block = "\n\n".join(lines) if lines else "No facilities were found."

    return f"""You are CareGrid, a healthcare intelligence assistant for India.
You help healthcare planners and patients find reliable medical facilities using evidence-based trust scores.

User query: "{query}"

Top recommended facilities (ranked by trust score and evidence):
{facility_block}

Please respond with exactly three sections using these headings:

AI SUMMARY:
Write 2-3 sentences summarising why these facilities were recommended and what the user should know.

REASONING:
Write 1-2 sentences explaining the key factors (trust score, readiness, capabilities) that drove the ranking.

NEXT STEPS:
Write 1-2 sentences advising the user on what to verify or do before acting on these recommendations.

Important rules:
- Only use the facility data provided above. Do not invent details.
- Be factual, concise, and medically cautious.
- If warnings exist, mention them briefly.
- Do not add bullet points or markdown beyond the three sections above.
"""


def _parse_response(text: str) -> dict[str, Optional[str]]:
    sections: dict[str, Optional[str]] = {
        "ai_summary": None,
        "ai_reasoning": None,
        "ai_next_steps": None,
    }
    mapping = {
        "AI SUMMARY:": "ai_summary",
        "REASONING:": "ai_reasoning",
        "NEXT STEPS:": "ai_next_steps",
    }
    current_key: Optional[str] = None
    buffer: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        matched_header = next((h for h in mapping if line.upper().startswith(h)), None)
        if matched_header:
            if current_key and buffer:
                sections[current_key] = " ".join(buffer).strip()
            current_key = mapping[matched_header]
            remainder = line[len(matched_header):].strip()
            buffer = [remainder] if remainder else []
        elif current_key is not None and line:
            buffer.append(line)

    if current_key and buffer:
        sections[current_key] = " ".join(buffer).strip()

    return sections


def get_ai_fields(
    query: str,
    recommendations: list[dict[str, Any]],
) -> dict[str, Optional[str]]:
    """
    Call Gemini 1.5 Flash via the official google-genai SDK to generate
    AI summary fields for the agent response.

    Returns a dict with:
      ai_summary, ai_reasoning, ai_next_steps,
      model_used, model_provider, agent_mode

    All values are None on any failure -- rule-based results are never broken.
    """
    empty: dict[str, Optional[str]] = {
        "ai_summary": None,
        "ai_reasoning": None,
        "ai_next_steps": None,
        "model_used": None,
        "model_provider": None,
        "agent_mode": "rule-based",
    }

    if not _GENAI_AVAILABLE:
        logger.warning("google-genai package not installed. Run: pip install google-genai")
        return empty

    api_key = _load_api_key()
    if not api_key or api_key == "your_gemini_api_key_here":
        logger.info("GEMINI_API_KEY not set -- skipping AI summary generation.")
        return empty

    if not recommendations:
        logger.info("No recommendations -- skipping Gemini call.")
        return empty

    try:
        client = genai.Client(api_key=api_key)
        prompt = _build_prompt(query, recommendations)

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=400,
            ),
        )

        parsed = _parse_response(response.text)
        return {
            **parsed,
            "model_used": "gemini-1.5-flash",
            "model_provider": "Google",
            "agent_mode": "hybrid",
        }

    except Exception as exc:
        logger.error("Gemini AI summary failed: %s", exc)
        return {
            **empty,
            "ai_reasoning": f"AI summary temporarily unavailable: {type(exc).__name__}",
            "agent_mode": "rule-based",
        }
