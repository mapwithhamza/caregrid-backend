"""
agent_core.capability_taxonomy — Healthcare capability vocabulary + safe matching.

This module is the single source of truth for what "ICU" means, what
"dialysis" means, and so on. Every other module that needs to match
clinical terms in raw facility text **must** go through the helpers
defined here so we get a single, audited, false-positive-free matcher.

Why the helpers exist (Stage 16)
--------------------------------
A naive ``term.lower() in text.lower()`` substring scan caused several
false positives in production smoke runs, e.g. the token ``ER`` matching
inside ``Stapler Circumcision``, ``cataract surgERy``, ``cEntERs`` —
which then promoted unrelated facilities as emergency-care evidence.

The matcher in this module fixes that with three rules:

1. Matching is case-insensitive (after :func:`normalize_text`).
2. Multi-word phrases match as phrases, not interleaved tokens.
3. Short terms (length ≤ 3 chars) and any term that contains a digit or
   a non-alpha symbol (``/``, ``x``, ``&``, ``:``) require **strict
   word boundaries** on both sides — they cannot match inside a longer
   word.

So ``ER`` matches in ``"ER department"`` and ``"Surgery; ER triage"``
but **not** in ``"centers"``, ``"Stapler"``, ``"refractive surgery"``,
``"ear surgery"``.

Public helpers
--------------
- :func:`normalize_text(text)` — lowercase + collapse whitespace.
- :func:`term_matches(text, term)` — single-term boolean match using
  the rules above.
- :func:`find_matching_terms(text, terms)` — return the subset of
  ``terms`` that occur in ``text``, longest first.
- :func:`find_capabilities_in_text(text)` — scan all capabilities and
  return the IDs whose keywords / synonyms / strong-evidence terms are
  present in ``text``. Used by the intent parser.

These helpers are pure — no IO, no globals, no side effects — so they
are safe to call from tight loops and tests.
"""

from __future__ import annotations

import re
from typing import TypedDict


class Capability(TypedDict):
    capability_id: str
    display_name: str
    keywords: list[str]
    synonyms: list[str]
    strong_evidence_keywords: list[str]
    supporting_equipment: list[str]
    required_staff: list[str]
    high_acuity: bool
    web_search_terms: list[str]


# ---------------------------------------------------------------------------
# Safe term matching (Stage 16) — public helpers
# ---------------------------------------------------------------------------

# Terms ≤ this length always require word-boundary matching.
_SHORT_TERM_LEN = 3

# Characters that, if present in a term, force word-boundary matching even if
# the term is longer than _SHORT_TERM_LEN. These cover healthcare-specific
# tokens that are easy to false-match inside longer words / dates / IDs.
_BOUNDARY_FORCING_CHARS = re.compile(r"[0-9/x:&]")

# A "word character" for our boundary purposes. We treat letters and digits
# as word chars so ``ER`` won't match inside ``ER01``, ``stER``, ``cEntERs``.
_WORD_CHAR = re.compile(r"[a-z0-9]")


def normalize_text(text: str) -> str:
    """
    Lowercase and collapse whitespace for safe matching.

    Returns ``""`` for ``None``, non-strings, or empty input. Punctuation
    is preserved because some clinical tokens depend on it (``A&E``,
    ``24/7``, ``24x7``).
    """
    if text is None:
        return ""
    s = str(text)
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip().lower()


def _needs_boundary(term_lower: str) -> bool:
    """
    Decide whether ``term_lower`` must be matched with strict word
    boundaries.

    True when the term is short (≤ 3 chars) **or** contains digits / one
    of the boundary-forcing characters. False otherwise — longer purely
    alphabetic terms can use plain substring matching, which is safe.
    """
    if len(term_lower) <= _SHORT_TERM_LEN:
        return True
    return bool(_BOUNDARY_FORCING_CHARS.search(term_lower))


def _boundary_pattern(term_lower: str) -> re.Pattern[str]:
    """
    Build a compiled regex that matches ``term_lower`` only when bounded
    by string start/end or a non-word character on each side.
    """
    escaped = re.escape(term_lower)
    return re.compile(r"(?:^|[^a-z0-9])" + escaped + r"(?:[^a-z0-9]|$)")


def term_matches(text: str, term: str) -> bool:
    """
    Does ``term`` occur in ``text`` under the safe-matching rules?

    Rules
    -----
    - Both inputs are lowercased and whitespace-collapsed first.
    - Multi-word phrases match as phrases (the regex / substring keeps
      whitespace intact).
    - Short terms (≤ 3 chars) and any term containing a digit / ``/`` /
      ``x`` / ``:`` / ``&`` use strict word boundaries.
    - All other terms use plain substring matching.
    """
    haystack = normalize_text(text)
    needle = normalize_text(term)
    if not haystack or not needle:
        return False
    if _needs_boundary(needle):
        return bool(_boundary_pattern(needle).search(haystack))
    return needle in haystack


def find_matching_terms(text: str, terms: list[str]) -> list[str]:
    """
    Return the subset of ``terms`` that occur in ``text`` (longest first).

    Each term is matched using :func:`term_matches`; duplicates and
    empty entries are filtered. Output preserves longest-first order so
    callers that want the most specific hit can read element ``[0]``.
    """
    if not text or not terms:
        return []
    haystack = normalize_text(text)
    seen: set[str] = set()
    hits: list[str] = []
    for raw in terms:
        if not raw:
            continue
        needle = normalize_text(raw)
        if not needle or needle in seen:
            continue
        if _needs_boundary(needle):
            if _boundary_pattern(needle).search(haystack):
                seen.add(needle)
                hits.append(needle)
        else:
            if needle in haystack:
                seen.add(needle)
                hits.append(needle)
    hits.sort(key=len, reverse=True)
    return hits


# ---------------------------------------------------------------------------
# Capability vocabulary
# ---------------------------------------------------------------------------

_CAPABILITIES: list[Capability] = [
    {
        "capability_id": "ICU_CRITICAL_CARE",
        "display_name": "ICU / Critical Care",
        "keywords": ["ICU", "ICCU", "critical care", "intensive care", "CCU", "MICU", "SICU"],
        "synonyms": ["intensive care unit", "critical care unit", "medical ICU", "surgical ICU"],
        "strong_evidence_keywords": [
            "ventilator", "mechanical ventilation", "vasopressor", "critical care beds",
            "invasive monitoring", "arterial line", "central venous catheter",
        ],
        "supporting_equipment": [
            "ventilator", "cardiac monitor", "defibrillator", "infusion pump",
            "pulse oximeter", "arterial blood gas analyser",
        ],
        "required_staff": ["intensivist", "critical care nurse", "respiratory therapist"],
        "high_acuity": True,
        "web_search_terms": ["ICU beds hospital India", "critical care unit", "intensive care hospital"],
    },
    {
        "capability_id": "OXYGEN_SUPPORT",
        "display_name": "Oxygen Support",
        "keywords": ["oxygen", "O2 support", "oxygen therapy", "oxygen supply", "BiPAP", "CPAP"],
        "synonyms": ["supplemental oxygen", "piped oxygen", "oxygen concentrator", "high flow oxygen"],
        "strong_evidence_keywords": [
            "oxygen concentrator", "piped oxygen", "liquid oxygen plant",
            "high flow nasal cannula", "BiPAP machine", "CPAP machine", "non-invasive ventilation",
        ],
        "supporting_equipment": [
            "oxygen concentrator", "oxygen cylinder", "flow meter",
            "BiPAP machine", "CPAP machine", "oxygen manifold",
        ],
        "required_staff": ["respiratory therapist", "nurse"],
        "high_acuity": False,
        "web_search_terms": ["oxygen support hospital India", "oxygen therapy facility", "piped oxygen hospital"],
    },
    {
        # Stage 16: synonyms tightened. "ER" is kept in keywords because the
        # safe matcher word-bounds short tokens, so it can no longer leak
        # into "centers", "stapler", "refractive surgery", "cataract surgery",
        # etc. Strong evidence is restricted to clinically meaningful tokens
        # so a generic "surgery" or "treatment" cannot promote a record.
        "capability_id": "EMERGENCY_TRAUMA",
        "display_name": "Emergency & Trauma",
        "keywords": [
            "emergency", "trauma", "casualty", "accident", "A&E", "ER",
            "emergency room", "emergency department", "trauma centre",
            "trauma center",
        ],
        "synonyms": [
            "accident and emergency", "casualty ward", "trauma bay",
            "emergency ward",
        ],
        "strong_evidence_keywords": [
            # Clinically meaningful emergency-presence indicators only.
            "emergency department", "emergency room", "casualty ward",
            "trauma centre", "trauma center", "trauma bay",
            "ambulance", "24/7", "24x7", "round the clock",
            "critical care", "ventilator", "oxygen support",
            "triage", "resuscitation", "resuscitation bay",
            "ATLS", "level 1 trauma", "mass casualty", "FAST scan",
        ],
        "supporting_equipment": [
            "stretcher", "defibrillator", "emergency trolley", "trauma bay",
            "portable X-ray", "point-of-care ultrasound",
        ],
        "required_staff": ["emergency physician", "trauma surgeon", "emergency nurse", "paramedic"],
        "high_acuity": True,
        "web_search_terms": ["emergency hospital India", "trauma centre India", "24 hour emergency hospital"],
    },
    {
        "capability_id": "SURGERY",
        "display_name": "Surgery / Operation Theatre",
        "keywords": [
            "surgery", "operation theatre", "OT", "surgical", "laparoscopy",
            "operation", "robotic surgery", "orthopaedic surgery",
        ],
        "synonyms": ["operation room", "OR", "surgical unit", "theatre", "modular OT"],
        "strong_evidence_keywords": [
            "modular OT", "laminar flow OT", "laparoscopic surgery", "robotic surgery",
            "CSSD", "anaesthesia workstation", "electrosurgical unit",
        ],
        "supporting_equipment": [
            "operation table", "anaesthesia machine", "surgical lights",
            "electrosurgical unit", "laparoscope", "C-arm fluoroscopy",
        ],
        "required_staff": ["surgeon", "anaesthesiologist", "scrub nurse", "OT technician"],
        "high_acuity": False,
        "web_search_terms": ["surgical hospital India", "operation theatre hospital", "laparoscopic surgery India"],
    },
    {
        # Stage 16: dialysis vocabulary tightened. Removed bare "kidney" /
        # "renal" / "renal failure" from primary keywords because they
        # over-match ("kidney stones", "renal profile", "adrenal", urology
        # records). Specific phrases are kept in synonyms; the heavy-hitting
        # equipment / procedure names are in strong_evidence_keywords so
        # facilities with real haemodialysis gear outrank kidney-stone-only
        # records.
        "capability_id": "DIALYSIS_RENAL",
        "display_name": "Dialysis / Renal Care",
        "keywords": [
            "dialysis", "hemodialysis", "haemodialysis",
            "nephrology", "nephrologist",
            "CAPD", "peritoneal dialysis",
        ],
        "synonyms": [
            "renal replacement therapy", "kidney dialysis",
            "chronic kidney disease management",
            "kidney failure dialysis", "artificial kidney",
            "renal care", "renal unit", "renal dialysis",
            "AV fistula", "arteriovenous fistula",
            "vascular access for haemodialysis",
            "vascular access for hemodialysis",
        ],
        "strong_evidence_keywords": [
            "dialysis machine", "haemodialysis machine", "hemodialysis machine",
            "hemodialysis unit", "haemodialysis unit",
            "RO water plant", "AKI management", "CRRT",
            "continuous renal replacement therapy",
        ],
        "supporting_equipment": [
            "dialysis machine", "RO water plant", "dialysis chair",
            "vascular access kit", "CRRT machine",
        ],
        "required_staff": ["nephrologist", "dialysis nurse", "dialysis technician"],
        "high_acuity": True,
        "web_search_terms": ["dialysis centre India", "hemodialysis hospital India", "kidney dialysis hospital"],
    },
    {
        "capability_id": "ONCOLOGY",
        "display_name": "Oncology / Cancer Care",
        "keywords": [
            "oncology", "cancer", "chemotherapy", "radiation", "radiotherapy",
            "tumour", "tumor", "chemo",
        ],
        "synonyms": [
            "cancer treatment", "oncology unit", "chemo ward", "radiation therapy",
            "cancer care centre",
        ],
        "strong_evidence_keywords": [
            "linear accelerator", "LINAC", "chemotherapy protocol", "bone marrow transplant",
            "radiation oncology", "targeted therapy", "immunotherapy",
        ],
        "supporting_equipment": [
            "linear accelerator", "chemotherapy infusion pump",
            "radiation therapy machine", "PET-CT scanner", "brachytherapy unit",
        ],
        "required_staff": ["oncologist", "radiation oncologist", "oncology nurse", "medical physicist"],
        "high_acuity": True,
        "web_search_terms": ["cancer hospital India", "oncology centre India", "chemotherapy hospital India"],
    },
    {
        "capability_id": "MATERNAL_CARE",
        "display_name": "Maternal Care / Obstetrics",
        "keywords": [
            "maternity", "obstetrics", "delivery", "labour", "labor",
            "antenatal", "postnatal", "gynaecology", "gynecology", "pregnancy",
        ],
        "synonyms": ["labour ward", "delivery room", "maternity ward", "obstetric unit", "birth centre"],
        "strong_evidence_keywords": [
            "C-section", "caesarean", "LSCS", "high risk pregnancy",
            "obstetric ICU", "labour room", "epidural", "CTG monitoring",
        ],
        "supporting_equipment": [
            "delivery table", "CTG machine", "neonatal resuscitation table",
            "foetal monitor", "epidural pump",
        ],
        "required_staff": ["obstetrician", "gynaecologist", "midwife", "labour room nurse"],
        "high_acuity": False,
        "web_search_terms": ["maternity hospital India", "obstetrics hospital", "delivery hospital India"],
    },
    {
        "capability_id": "NEONATAL_PEDIATRIC",
        "display_name": "Neonatal / Paediatric Care",
        "keywords": [
            "NICU", "neonatal", "newborn", "paediatric", "pediatric", "PICU",
            "child", "infant", "neonatal care",
        ],
        "synonyms": [
            "neonatal ICU", "paediatric ICU", "paediatric ward",
            "children's hospital", "newborn care unit",
        ],
        "strong_evidence_keywords": [
            "incubator", "neonatal ventilator", "phototherapy", "neonatal resuscitation",
            "preterm care", "kangaroo mother care", "surfactant therapy",
        ],
        "supporting_equipment": [
            "incubator", "phototherapy lamp", "neonatal ventilator",
            "pulse oximeter paediatric", "neonatal resuscitation table",
        ],
        "required_staff": ["neonatologist", "paediatrician", "NICU nurse", "paediatric nurse"],
        "high_acuity": True,
        "web_search_terms": ["NICU hospital India", "neonatal care India", "paediatric hospital India"],
    },
    {
        "capability_id": "DIAGNOSTICS",
        "display_name": "Diagnostics / Imaging",
        "keywords": [
            "MRI", "CT scan", "X-ray", "radiology", "ultrasound", "pathology",
            "laboratory", "diagnostics", "imaging", "sonography", "ECG", "echo",
        ],
        "synonyms": [
            "diagnostic centre", "imaging centre", "radiology unit",
            "lab services", "clinical laboratory",
        ],
        "strong_evidence_keywords": [
            "3T MRI", "128-slice CT", "digital X-ray", "NABL accredited lab",
            "PET-CT", "mammography", "echocardiography",
        ],
        "supporting_equipment": [
            "MRI machine", "CT scanner", "X-ray machine",
            "ultrasound machine", "ECG machine", "NABL lab equipment",
        ],
        "required_staff": ["radiologist", "pathologist", "lab technician", "radiology technician"],
        "high_acuity": False,
        "web_search_terms": ["diagnostic hospital India", "MRI CT scan India", "NABL lab hospital"],
    },
    {
        "capability_id": "AMBULANCE",
        "display_name": "Ambulance Services",
        "keywords": [
            "ambulance", "emergency transport", "patient transport",
            "mobile ICU", "ALS ambulance", "BLS ambulance",
        ],
        "synonyms": ["advanced life support ambulance", "basic life support ambulance", "MICU ambulance"],
        "strong_evidence_keywords": [
            "advanced life support", "ALS ambulance", "mobile ICU",
            "paramedic staffed", "MICU ambulance", "GPS tracked ambulance",
        ],
        "supporting_equipment": [
            "ambulance", "portable defibrillator", "stretcher",
            "portable oxygen", "spinal board",
        ],
        "required_staff": ["paramedic", "EMT", "ambulance driver"],
        "high_acuity": False,
        "web_search_terms": ["ambulance service hospital India", "ALS ambulance India", "emergency transport hospital"],
    },
    {
        "capability_id": "BLOOD_BANK",
        "display_name": "Blood Bank",
        "keywords": [
            "blood bank", "blood transfusion", "blood storage", "plasma",
            "platelets", "blood components", "packed red cells",
        ],
        "synonyms": ["transfusion service", "blood component therapy", "blood centre"],
        "strong_evidence_keywords": [
            "NBTC licensed", "component separation", "apheresis",
            "cross-matching", "blood grouping", "irradiated blood",
        ],
        "supporting_equipment": [
            "blood storage refrigerator", "apheresis machine",
            "blood bag sealer", "centrifuge", "platelet agitator",
        ],
        "required_staff": ["transfusion medicine specialist", "blood bank technician"],
        "high_acuity": False,
        "web_search_terms": ["blood bank hospital India", "blood transfusion hospital India"],
    },
    {
        "capability_id": "TWENTY_FOUR_SEVEN",
        "display_name": "24/7 Services",
        "keywords": [
            "24/7", "24 hours", "round the clock", "always open",
            "all hours", "night services", "24x7", "round-the-clock",
        ],
        "synonyms": ["24-hour hospital", "24-hour emergency", "continuous care"],
        "strong_evidence_keywords": [
            "24 hour emergency", "24/7 ICU", "round the clock specialist",
            "night shift specialist", "24-hour pharmacy",
        ],
        "supporting_equipment": [],
        "required_staff": ["duty doctor", "night nurse", "on-call specialist"],
        "high_acuity": False,
        "web_search_terms": ["24 hour hospital India", "all night hospital", "24/7 emergency hospital"],
    },
    {
        "capability_id": "SPECIALIST_SUPPORT",
        "display_name": "Specialist Support",
        "keywords": [
            "specialist", "consultant", "cardiologist", "cardiac", "cardiology",
            "cathlab", "cath lab", "neurologist", "pulmonologist",
            "gastroenterologist", "multi-specialty", "super specialty",
        ],
        "synonyms": [
            "multi-specialty hospital", "super specialty hospital",
            "expert consultation", "specialist team",
        ],
        "strong_evidence_keywords": [
            "full-time consultant", "on-call specialist", "super specialty team",
            "multi-disciplinary team", "MDT", "cardiac catheterisation lab",
        ],
        "supporting_equipment": [],
        "required_staff": [
            "cardiologist", "neurologist", "pulmonologist", "gastroenterologist",
        ],
        "high_acuity": False,
        "web_search_terms": [
            "specialist hospital India", "multi-specialty hospital India",
            "super specialty hospital India",
        ],
    },
]

# Primary lookup index: capability_id → Capability
CAPABILITY_INDEX: dict[str, Capability] = {c["capability_id"]: c for c in _CAPABILITIES}


# ---------------------------------------------------------------------------
# Capability lookups
# ---------------------------------------------------------------------------

def get_capability(capability_id: str) -> Capability:
    """Return the Capability dict for the given ID. Raises KeyError if not found."""
    return CAPABILITY_INDEX[capability_id]


def list_capabilities() -> list[str]:
    """Return all capability IDs in definition order."""
    return [c["capability_id"] for c in _CAPABILITIES]


def find_capabilities_in_text(text: str) -> list[str]:
    """
    Scan ``text`` (case-insensitive, with safe word-boundary matching for
    short / symbol-bearing tokens) for capability keywords, synonyms,
    and strong_evidence_keywords. Returns a deduplicated list of
    matching capability IDs in definition order.

    This is the **only** public capability-detection entry point used by
    the intent parser and other call sites — it must use
    :func:`term_matches` so token-level false positives like ``ER``
    inside ``"centers"`` cannot leak in.
    """
    if not text:
        return []
    haystack = normalize_text(text)
    if not haystack:
        return []

    matched: list[str] = []
    for cap in _CAPABILITIES:
        search_terms = (
            cap["keywords"]
            + cap["synonyms"]
            + cap["strong_evidence_keywords"]
        )
        if find_matching_terms(haystack, search_terms):
            matched.append(cap["capability_id"])
    return matched


def get_high_acuity_capabilities() -> list[str]:
    """Return capability IDs where high_acuity is True."""
    return [c["capability_id"] for c in _CAPABILITIES if c["high_acuity"]]
