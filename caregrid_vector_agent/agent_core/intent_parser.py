from __future__ import annotations
import re
from typing import Optional

from agent_core.schemas import AgentIntent
from agent_core.capability_taxonomy import find_capabilities_in_text

# ---------------------------------------------------------------------------
# Location data — all Indian states, UTs, and major cities
# ---------------------------------------------------------------------------
_INDIA_STATES: list[str] = [
    # States (listed longest first so multi-word names win)
    "Arunachal Pradesh", "Andhra Pradesh", "Himachal Pradesh", "Madhya Pradesh",
    "Uttar Pradesh", "West Bengal", "Tamil Nadu", "Jammu and Kashmir",
    "Jammu & Kashmir", "Chhattisgarh", "Uttarakhand", "Jharkhand",
    "Karnataka", "Telangana", "Rajasthan", "Maharashtra", "Meghalaya",
    "Nagaland", "Mizoram", "Manipur", "Tripura", "Assam", "Gujarat",
    "Haryana", "Odisha", "Punjab", "Sikkim", "Kerala", "Bihar", "Goa",
    # Union Territories
    "Andaman and Nicobar Islands", "Dadra and Nagar Haveli", "Daman and Diu",
    "Lakshadweep", "Puducherry", "Pondicherry", "Chandigarh", "Ladakh",
    "Delhi",
]

_INDIA_CITIES: list[str] = [
    "Thiruvananthapuram", "Vishakhapatnam", "Visakhapatnam", "Bhubaneswar",
    "Trivandrum", "Coimbatore", "Ahmedabad", "Bangalore", "Bengaluru",
    "Hyderabad", "Chennai", "Kolkata", "Mumbai", "Delhi", "Pune",
    "Jaipur", "Lucknow", "Surat", "Kochi", "Chandigarh", "Indore",
    "Nagpur", "Bhopal", "Patna", "Ranchi", "Vadodara", "Noida",
    "Gurgaon", "Gurugram", "Faridabad", "Ghaziabad", "Meerut",
    "Varanasi", "Agra", "Kanpur", "Mysuru", "Mysore", "Hubballi",
    "Mangaluru", "Amritsar", "Ludhiana", "Jalandhar", "Gwalior",
    "Jodhpur", "Udaipur", "Kota", "Nashik", "Aurangabad", "Solapur",
    "Thane", "Srinagar", "Jammu", "Dehradun", "Haridwar", "Raipur",
    "Guwahati", "Imphal", "Shillong", "Aizawl", "Kohima", "Agartala",
    "Gangtok", "Itanagar", "Panaji",
]

# ---------------------------------------------------------------------------
# Facility type keyword map
# NOTE: "dental" is intentionally absent — it is a specialty modifier, not a
#       facility type. Only the word "dentist"/"dentists" maps to "dentist".
# ---------------------------------------------------------------------------
_FACILITY_TYPES: dict[str, list[str]] = {
    "hospital": ["hospital", "hospitals"],
    "clinic":   ["clinic", "clinics"],
    "doctor":   ["doctor", "doctors", "physician", "physicians"],
    "pharmacy": ["pharmacy", "pharmacies", "chemist", "chemists", "drugstore"],
    "dentist":  ["dentist", "dentists"],
}

# ---------------------------------------------------------------------------
# Trust preference triggers
# ---------------------------------------------------------------------------
_TRUST_TRIGGERS: dict[str, list[str]] = {
    "trusted": [
        "high trust", "trusted", "reliable", "verified", "trust score above",
        "trust_score above", "high recommendation readiness", "only recommended",
        "well known", "reputed", "reputable",
    ],
    "verification_ok": [
        "verify before", "with verification", "check before use",
        "usable with verification", "needs verification",
    ],
    "risky_allowed": [
        "any hospital", "include all", "all options", "include risky",
        "even low trust", "regardless of trust",
    ],
}

# ---------------------------------------------------------------------------
# Urgency triggers  (checked in priority order: emergency > urgent > routine)
# ---------------------------------------------------------------------------
_URGENCY_TRIGGERS: dict[str, list[str]] = {
    "emergency": [
        "life threatening", "life-threatening", "critical emergency",
        "urgent emergency", "immediate emergency",
        "emergency",       # broad match last within this tier
    ],
    "urgent": [
        "urgent", "urgently", "asap", "as soon as possible",
        "immediately", "right now", "today", "tonight",
    ],
    "routine": [
        "routine", "planned", "scheduled", "elective",
        "non-urgent", "when available", "no rush",
    ],
}

# ---------------------------------------------------------------------------
# Other modifier triggers
# ---------------------------------------------------------------------------
_PROXIMITY_TRIGGERS: list[str] = [
    "near me", "nearby", "nearest", "closest",
    "close to me", "in my area", "around me", "within reach",
]

_WEB_VERIFICATION_TRIGGERS: list[str] = [
    "verify online", "web search", "check online",
    "internet verification", "tavily", "search web",
    "web verified", "online check",
]

_VECTOR_SEARCH_TRIGGERS: list[str] = [
    "vector search", "semantic search", "similarity search",
    "search database", "search the database",
]

# Regex for explicit numeric trust threshold: "trust_score above 0.8"
_TRUST_SCORE_RE = re.compile(
    r"trust[_\s]?score\s*(?:above|>|greater\s+than)\s*(\d+\.?\d*)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(query: str) -> str:
    """Lowercase, collapse runs of whitespace, strip ends."""
    return re.sub(r"\s+", " ", query.strip().lower())


def _contains(text: str, phrases: list[str]) -> bool:
    """Case-insensitive substring search for any phrase in the list."""
    t = text.lower()
    return any(p.lower() in t for p in phrases)


def _detect_state(text: str, candidates: list[str]) -> Optional[str]:
    """Return the first state name found, matching longest names first."""
    t = text.lower()
    for state in sorted(candidates, key=len, reverse=True):
        if state.lower() in t:
            return state
    return None


def _detect_city(text: str) -> Optional[str]:
    """Return the first city name found, matching longest names first."""
    t = text.lower()
    for city in sorted(_INDIA_CITIES, key=len, reverse=True):
        if city.lower() in t:
            return city
    return None


def _detect_facility_type(
    text: str,
    known_facility_types: list[str] | None,
) -> Optional[str]:
    """Return the first matching facility type keyword found in text."""
    types_to_check = known_facility_types or list(_FACILITY_TYPES.keys())
    t = text.lower()
    for ftype in types_to_check:
        triggers = _FACILITY_TYPES.get(ftype, [ftype])
        if any(tr.lower() in t for tr in triggers):
            return ftype
    return None


def _detect_trust_preference(text: str) -> str:
    for pref, triggers in _TRUST_TRIGGERS.items():
        if _contains(text, triggers):
            return pref
    return "unspecified"


def _detect_urgency(text: str) -> str:
    for level, triggers in _URGENCY_TRIGGERS.items():
        if _contains(text, triggers):
            return level
    return "unspecified"


def _detect_min_trust_score(text: str) -> Optional[float]:
    """Extract an explicit numeric trust threshold if present."""
    m = _TRUST_SCORE_RE.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_query_intent(
    query: str,
    known_states: list[str] | None = None,
    known_facility_types: list[str] | None = None,
) -> AgentIntent:
    """
    Parse a natural-language healthcare query into a structured AgentIntent.

    Pure keyword/regex — no LLM, no Tavily, no Databricks calls.

    Parameters
    ----------
    query:
        Raw user query string.
    known_states:
        Restrict state detection to this list. Defaults to all Indian states/UTs.
    known_facility_types:
        Restrict facility-type detection to this subset. Defaults to all five types.
    """
    normalized = _normalize(query)
    state_candidates = known_states if known_states is not None else _INDIA_STATES

    capabilities    = find_capabilities_in_text(query)
    state           = _detect_state(normalized, state_candidates)
    city            = _detect_city(normalized)
    facility_type   = _detect_facility_type(normalized, known_facility_types)
    trust_pref      = _detect_trust_preference(normalized)
    urgency         = _detect_urgency(normalized)
    min_ts          = _detect_min_trust_score(query)
    proximity       = _contains(normalized, _PROXIMITY_TRIGGERS)
    web_verify      = _contains(normalized, _WEB_VERIFICATION_TRIGGERS)
    vector_search   = _contains(normalized, _VECTOR_SEARCH_TRIGGERS)

    # location: prefer city when available, else fall back to state
    location = city or state

    return AgentIntent(
        raw_query=query,
        original_query=query,
        normalized_query=normalized,
        capabilities_required=capabilities,
        state=state,
        city=city,
        location=location,
        facility_type=facility_type,
        trust_preference=trust_pref,
        urgency=urgency,
        min_trust_score=min_ts,
        proximity_requested=proximity,
        web_verification_requested=web_verify,
        vector_search_requested=vector_search,
    )


def parse_intent(query: str) -> AgentIntent:
    """Backward-compatible wrapper around parse_query_intent."""
    return parse_query_intent(query)
