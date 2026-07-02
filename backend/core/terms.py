"""Term extraction logic for entity names.

Two-pass system:
  Pass 1: Segment entity names into tokens and assign initial scores based on
           wordninja language model frequency.
  Pass 2: Reclassify tokens using parent/sibling context into business,
           operations, or language categories.
"""

import wordninja


DOMAIN_TERMS = {"gss", "gpa", "immuta", "transact", "uuid", "crm", "hie", "eoi", "ppl", "classifier"}

BUSINESS_TERMS = {
    "gss", "gpa", "immuta", "transact", "crm", "hie", "eoi", "ppl",
    "classifier", "galleri", "commercial", "artemis", "clinical",
    "oncology", "genomic", "assay", "biomarker", "cohort", "specimen",
    "analyte", "variant", "pipeline", "flowcell", "sequencing",
    "illumina", "cfna", "methylation", "grail",
}

OPERATIONS_TERMS = {
    "created", "modified", "updated", "deleted", "archived",
    "version", "count", "total", "sum", "avg", "average",
    "timestamp", "status", "source", "owner", "author",
    "enabled", "disabled", "active", "inactive", "valid", "invalid",
    "start", "stop", "begin", "finish",
    "sync", "async", "batch", "queue", "job", "task", "worker",
    "error", "warning", "success", "failed", "pending", "completed",
    "retry", "attempt", "timeout", "duration", "elapsed",
    "config", "setting", "param", "option", "default",
    "index", "offset", "limit", "page", "size", "length",
    "hash", "token", "session", "request", "response",
    "insert", "update", "delete", "select", "merge", "upsert",
    "load", "extract", "transform", "etl", "ingestion",
}

KNOWN_COMPOUNDS = {
    "signoff", "signup", "signin", "logout", "login",
    "datetime", "timestamp", "dataset", "workflow", "lookup",
    "dropdown", "checkbox", "frontend", "backend", "endpoint",
    "username", "filename", "metadata", "namespace", "lifecycle",
    "rollback", "rollup", "cleanup", "timeout", "callback",
    "upstream", "downstream", "inbound", "outbound",
    "healthcare", "workflow", "dataflow", "pipeline",
}

GENERIC_STOPWORDS = {
    "a", "an", "at", "by", "for", "in", "is", "it", "of", "on", "or", "to",
    "the", "and", "not", "no", "be", "do", "id", "type", "name", "key",
    "has", "had", "was", "are", "but", "if", "so", "as", "up", "out",
    "date", "time", "num", "flag", "code", "col", "row", "val", "tmp",
    "new", "old", "all", "set", "get", "max", "min", "end", "log",
}


def segment_name(name: str) -> list[str]:
    """Split a concatenated entity name into tokens, including compound bigrams/trigrams."""
    clean = name.lower().replace("_", "").replace("-", "")
    if not clean:
        return []
    parts = [p for p in wordninja.split(clean) if p]
    if not parts:
        return []

    merged = []
    i = 0
    while i < len(parts):
        matched = False
        for length in range(min(4, len(parts) - i), 1, -1):
            candidate = "".join(parts[i:i + length])
            if candidate in DOMAIN_TERMS:
                merged.append(candidate)
                i += length
                matched = True
                break
        if not matched:
            merged.append(parts[i])
            i += 1

    compounds = set()
    lm = wordninja.DEFAULT_LANGUAGE_MODEL
    for window in (2, 3):
        for i in range(len(merged) - window + 1):
            compound = "".join(merged[i:i + window])
            if compound in DOMAIN_TERMS or compound in KNOWN_COMPOUNDS:
                compounds.add(compound)
                continue
            cost = lm._wordcost.get(compound)
            if cost is not None and len(compound) >= 4:
                compounds.add(compound)

    all_tokens = list(merged) + sorted(compounds)
    return all_tokens


def tokenize_entity(entity_name: str) -> list[tuple[str, str, int]]:
    """Pass 1: Segment name into tokens with initial scores. All typed as 'language'.

    Returns list of (term_name, term_type, score) tuples.
    """
    lm = wordninja.DEFAULT_LANGUAGE_MODEL
    HIGH_FREQ_CEILING = 9.0
    MED_FREQ_CEILING = 11.5
    LOW_FREQ_CEILING = 13.0

    tokens = segment_name(entity_name)
    results = []

    for token in tokens:
        if not token:
            continue
        t = token.lower().strip("_")
        if not t or t in GENERIC_STOPWORDS or len(t) < 2:
            continue

        cost = lm._wordcost.get(t)

        if cost is None:
            score = 90 if len(t) <= 5 else 75
        elif cost >= LOW_FREQ_CEILING:
            score = 70
        elif cost >= MED_FREQ_CEILING:
            ratio = (cost - MED_FREQ_CEILING) / (LOW_FREQ_CEILING - MED_FREQ_CEILING)
            score = int(30 + ratio * 40)
        elif cost >= HIGH_FREQ_CEILING:
            ratio = (cost - HIGH_FREQ_CEILING) / (MED_FREQ_CEILING - HIGH_FREQ_CEILING)
            score = int(10 + ratio * 20)
        else:
            score = min(10 + len(t), 20) if len(t) >= 3 else 0

        if score >= 10:
            results.append((t, "language", min(score, 100)))

    return results


def classify_with_context(
    entity_terms: list[dict],
    parent_terms: list[str],
    sibling_terms: dict[str, list[str]],
    sibling_count: int,
) -> list[tuple[str, str, int]]:
    """Pass 2: Reclassify terms using parent and sibling context.

    Args:
        entity_terms: The entity's current terms [{"name", "type", "score"}].
        parent_terms: List of term names from the parent entity.
        sibling_terms: Dict of sibling_fqn -> [term_names] for siblings.
        sibling_count: Total number of siblings.

    Returns:
        Updated list of (term_name, term_type, score) tuples.
    """
    cooccurrence: dict[str, int] = {}
    for terms_list in sibling_terms.values():
        seen = set()
        for t in terms_list:
            if t not in seen:
                seen.add(t)
                cooccurrence[t] = cooccurrence.get(t, 0) + 1

    results = []
    for term in entity_terms:
        t = term.get("name")
        base_score = term.get("score") or 0
        if not t:
            continue

        if t in BUSINESS_TERMS:
            term_type = "business"
            score = max(base_score, 80)
        elif t in OPERATIONS_TERMS:
            term_type = "operations"
            score = max(base_score, 40)
        else:
            term_type = "language"
            score = base_score

        if t in parent_terms:
            score = min(score + 15, 100)

        if sibling_count > 1:
            count = cooccurrence.get(t, 0)
            if count >= 2:
                share = count / sibling_count
                boost = int(share * 30)
                score = min(score + boost, 100)

        if term_type == "language" and t in parent_terms and cooccurrence.get(t, 0) >= 3:
            term_type = "business"
            score = max(score, 60)

        results.append((t, term_type, score))

    return results
