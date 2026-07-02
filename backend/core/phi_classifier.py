"""PHI/PII classification logic for entity names.

Provides pattern sets and scoring functions for a 5-pass classification pipeline:
  Pass 1: Name pattern matching (pure name-based)
  Pass 2: Term-based scoring (uses extracted terms from terms table)
  Pass 3: Child-to-parent boosting
  Pass 4: Sibling-to-sibling boosting
  Pass 5: Score normalization and propagation
"""

from core.terms import segment_name, GENERIC_STOPWORDS


PHI_PATTERNS = {
    "patient", "diagnosis", "icd", "cpt", "mrn", "specimen",
    "clinical", "pathology", "genomic", "variant", "tumor",
    "treatment", "medication", "prescription", "lab", "result",
    "provider", "physician", "hospital", "encounter", "admission",
    "discharge", "prognosis", "symptom", "condition", "procedure",
    "surgery", "therapy", "dosage", "allergy", "immunization",
    "radiology", "imaging", "biopsy", "histology", "cytology",
    "hemoglobin", "glucose", "cholesterol", "blood", "plasma",
    "serum", "urine", "vital", "pulse", "heartrate", "oxygen",
    "insurance", "beneficiary", "claim", "copay", "deductible",
}

PII_PATTERNS = {
    "email", "ssn", "phone", "mobile", "address", "street",
    "city", "zip", "postal", "dob", "birth", "age", "gender",
    "firstname", "lastname", "fullname", "username", "password",
    "account", "card", "bank", "routing", "license", "passport",
    "national", "social", "security", "driver", "taxpayer",
    "salary", "income", "wage", "compensation", "payroll",
    "ethnicity", "race", "religion", "marital", "spouse",
    "dependent", "guardian", "emergency", "contact",
}

PHI_TERM_BOOSTERS = {
    "patient": 20, "clinical": 18, "specimen": 20, "genomic": 15,
    "variant": 12, "tumor": 18, "diagnosis": 20, "treatment": 15,
    "medication": 15, "pathology": 18, "lab": 10, "assay": 12,
    "biomarker": 15, "methylation": 12, "sequencing": 10,
    "oncology": 18, "classifier": 8, "flowcell": 8,
}

PII_TERM_BOOSTERS = {
    "email": 25, "phone": 20, "address": 20, "account": 12,
    "billing": 15, "payment": 15, "card": 18, "bank": 18,
    "username": 15, "password": 25, "login": 10, "birth": 20,
    "name": 15, "contact": 12, "salary": 18, "income": 15,
}


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
