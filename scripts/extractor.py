"""LLM-based entity and relation extraction.

Uses Anthropic Claude (primary) or Groq (fallback) to extract:
entities (name, type), relations (subject, predicate, object),
key facts, and topic tags from a chunk of text.
"""
import json
import os
from typing import Tuple, List
from urllib.request import Request, urlopen
from urllib.error import URLError

from models import Entity, Relation, EntityType
from config import (
    GROQ_API_KEY, GROQ_MODEL, GROQ_API_URL,
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_API_URL,
    USE_ANTHROPIC
)

EXTRACT_PROMPT = """You are an entity and relation extraction engine. Given a text chunk, extract:

1. ENTITIES: Named people, organizations, projects, concepts, places, events
2. RELATIONS: Triples (subject, predicate, object) connecting entities
3. TOPICS: 2-5 topic tags for classification

Respond ONLY with valid JSON in this exact format:
{
  "entities": [
    {"name": "exact name", "type": "person|org|project|concept|place|event"}
  ],
  "relations": [
    {"subject": "entity name", "predicate": "verb phrase", "object": "entity name", "confidence": 0.9}
  ],
  "topics": ["tag1", "tag2"],
  "quality_score": 0.7
}

Rules:
- Normalize entity names (e.g., "Vincent W" not "Vincent" and "Vincent W." separately)
- Use active voice for predicates (e.g., "works at", "founded", "located in")
- quality_score (0-1): how information-rich this chunk is
- If the chunk is low-quality (boilerplate, navigation, etc.), return quality_score < 0.3

TEXT CHUNK:
"""


def _call_anthropic(content: str) -> dict:
    """Call Anthropic Claude API for extraction."""
    api_key = ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("No Anthropic API key")

    payload = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2000,
        "messages": [
            {"role": "user", "content": EXTRACT_PROMPT + content[:8000]}
        ],
    }).encode("utf-8")

    req = Request(
        ANTHROPIC_API_URL,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode())
        text = result["content"][0]["text"]
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return json.loads(text.strip())


def _call_groq(content: str) -> dict:
    """Call Groq API for extraction."""
    api_key = GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("No Groq API key")

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise entity extraction engine. Output only valid JSON."},
            {"role": "user", "content": EXTRACT_PROMPT + content[:8000]}
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"}
    }).encode("utf-8")

    req = Request(
        GROQ_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
        text = result["choices"][0]["message"]["content"]
        return json.loads(text)


def extract_entities_llm(content: str) -> Tuple[List[Entity], List[Relation], float]:
    """Extract entities and relations from content using LLM.

    Tries Anthropic first (better quality), falls back to Groq (free/fast).
    Returns: (entities, relations, quality_score)
    """
    data = None

    # Try Anthropic first
    if USE_ANTHROPIC or os.getenv("ANTHROPIC_API_KEY"):
        try:
            data = _call_anthropic(content)
        except Exception as e:
            pass  # Fall through to Groq

    # Fall back to Groq
    if data is None:
        try:
            data = _call_groq(content)
        except Exception as e:
            return [], [], 0.5

    entities = []
    for e in data.get("entities", []):
        try:
            etype = EntityType(e.get("type", "concept"))
        except ValueError:
            etype = EntityType.CONCEPT
        entities.append(Entity(
            name=e["name"],
            entity_type=etype
        ))

    relations = []
    for r in data.get("relations", []):
        relations.append(Relation(
            subject=r["subject"],
            predicate=r["predicate"],
            object=r["object"],
            confidence=r.get("confidence", 0.8)
        ))

    quality = data.get("quality_score", 0.5)
    return entities, relations, quality
