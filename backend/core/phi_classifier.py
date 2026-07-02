"""PHI/PII classification logic for entity names.

Provides pattern sets and scoring functions for a 5-pass classification pipeline:
  Pass 1: Name pattern matching (pure name-based)
  Pass 2: Term-based scoring (uses extracted terms from terms table)
  Pass 3: Child-to-parent boosting
  Pass 4: Sibling-to-sibling boosting
  Pass 5: Score normalization and propagation

Pattern sets are loaded from core/config/phi_classifier.json and can be
customized per deployment without modifying code.
"""

import json
from pathlib import Path

from core.terms import segment_name, GENERIC_STOPWORDS

_CONFIG_PATH = Path(__file__).parent / "config" / "phi_classifier.json"


def _load_config():
    with open(_CONFIG_PATH) as f:
        return json.load(f)


_config = _load_config()

PHI_PATTERNS = set(_config.get("phi_patterns", []))
PII_PATTERNS = set(_config.get("pii_patterns", []))
PHI_TERM_BOOSTERS = _config.get("phi_term_boosters", {})
PII_TERM_BOOSTERS = _config.get("pii_term_boosters", {})


def reload_config():
    """Reload pattern sets from the JSON config file."""
    global PHI_PATTERNS, PII_PATTERNS, PHI_TERM_BOOSTERS, PII_TERM_BOOSTERS
    cfg = _load_config()
    PHI_PATTERNS = set(cfg.get("phi_patterns", []))
    PII_PATTERNS = set(cfg.get("pii_patterns", []))
    PHI_TERM_BOOSTERS = cfg.get("phi_term_boosters", {})
    PII_TERM_BOOSTERS = cfg.get("pii_term_boosters", {})


def score_by_name(entity_name: str) -> tuple[int, int]:
    """Pass 1: Score entity based on name patterns.

    Returns (phi_score, pii_score) based on pattern matches in the entity name.
    """
    tokens = segment_name(entity_name)
    token_set = {t.lower().strip("_") for t in tokens if t.lower().strip("_") not in GENERIC_STOPWORDS}

    phi_score = 0
    pii_score = 0

    for token in token_set:
        if token in PHI_PATTERNS:
            phi_score += 25
        if token in PII_PATTERNS:
            pii_score += 25

    return (min(phi_score, 80), min(pii_score, 80))


def score_by_terms(entity_terms: list[str], current_phi: int, current_pii: int) -> tuple[int, int]:
    """Pass 2: Adjust scores based on extracted terms from the terms table.

    Returns updated (phi_score, pii_score).
    """
    phi_boost = 0
    pii_boost = 0

    for term in entity_terms:
        t = term.lower()
        if t in PHI_TERM_BOOSTERS:
            phi_boost += PHI_TERM_BOOSTERS[t]
        if t in PII_TERM_BOOSTERS:
            pii_boost += PII_TERM_BOOSTERS[t]

    return (
        min(current_phi + phi_boost, 90),
        min(current_pii + pii_boost, 90),
    )


def compute_child_boost(child_phi: int, child_pii: int) -> int:
    """Compute boost score (5-10) that a child provides to its parent."""
    max_score = max(child_phi, child_pii)
    if max_score >= 60:
        return 10
    elif max_score >= 40:
        return 8
    elif max_score >= 20:
        return 6
    return 5


def compute_sibling_boost(sibling_phi: int, sibling_pii: int) -> int:
    """Compute boost score (5-10) from a sibling entity."""
    max_score = max(sibling_phi, sibling_pii)
    if max_score >= 60:
        return 8
    elif max_score >= 40:
        return 6
    return 5
