"""Fast heuristic scoring for chunks. No LLM calls — pure regex and statistics."""
import re
import math
from datetime import datetime, timezone
from models import Score


# Common English stop words to exclude from density calculation
STOP_WORDS = set("a an the is are was were be been being have has had do does did "
                 "will would shall should may might can could of in to for with on at "
                 "by from as into through during before after above below between "
                 "and or but not no nor so yet both either neither each every all "
                 "any few more most other some such than too very it its he she they "
                 "his her their this that these those i you we my your our".split())

# Patterns for entity detection (capitalized multi-word sequences)
ENTITY_PATTERN = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b')
# Also catch acronyms
ACRONYM_PATTERN = re.compile(r'\b[A-Z]{2,}\b')


def count_entities_regex(text: str) -> int:
    """Count potential named entities using capitalization heuristics."""
    # Skip headings (lines starting with #)
    lines = [l for l in text.split("\n") if not l.strip().startswith("#")]
    body = "\n".join(lines)

    entities = set()
    for m in ENTITY_PATTERN.finditer(body):
        # Skip sentence starters (rough: preceded by . or start of text)
        start = m.start()
        if start > 0 and body[start - 1] not in ".!?\n":
            entities.add(m.group().lower())
        elif start > 1 and body[start - 2] in ".!?":
            pass  # likely sentence starter, skip
        else:
            entities.add(m.group().lower())

    for m in ACRONYM_PATTERN.finditer(body):
        if m.group() not in ("I", "A", "OK", "US", "UK"):
            entities.add(m.group().lower())

    return len(entities)


def compute_info_density(text: str) -> float:
    """Ratio of unique non-stop-words to total words. Higher = more informative."""
    words = re.findall(r'\b\w+\b', text.lower())
    if not words:
        return 0.0
    content_words = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    if not content_words:
        return 0.0
    unique = len(set(content_words))
    return unique / len(content_words)


def fast_score(chunk_id: str, content: str, source_id: str = "",
               created_at: str = None) -> Score:
    """Compute a fast heuristic score (0-1) for a chunk. No LLM calls.

    Components (weighted):
    - Length score (0.2): optimal length ~500-2000 chars
    - Entity density (0.3): more entities = more valuable
    - Info density (0.3): unique terms / total terms
    - Recency (0.2): newer content scores higher
    """
    if not content or not content.strip():
        return Score(chunk_id=chunk_id, fast_score=0.05, entity_count=0,
                     info_density=0.0, recency_score=0.0)

    # Length score: bell curve peaking at 500-2000 chars
    length = len(content)
    if length < 50:
        length_score = 0.1
    elif length < 200:
        length_score = 0.4
    elif length <= 2000:
        length_score = 1.0
    elif length <= 5000:
        length_score = 0.7
    else:
        length_score = 0.4

    # Entity density
    entity_count = count_entities_regex(content)
    entity_score = min(1.0, entity_count / 5.0)  # cap at 5 entities

    # Information density
    info_density = compute_info_density(content)

    # Recency score (decay over 30 days)
    if created_at:
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - created).days
            recency_score = max(0.1, 1.0 - (age_days / 30.0))
        except (ValueError, TypeError):
            recency_score = 0.5
    else:
        recency_score = 0.5

    # Weighted combination
    fast = (
        0.2 * length_score +
        0.3 * entity_score +
        0.3 * info_density +
        0.2 * recency_score
    )

    return Score(
        chunk_id=chunk_id,
        fast_score=round(min(1.0, max(0.0, fast)), 4),
        entity_count=entity_count,
        info_density=round(info_density, 4),
        recency_score=round(recency_score, 4)
    )
