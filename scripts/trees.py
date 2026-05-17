"""Stage 4: Tree state management — source, topic, and global trees.

Manages L0 buffers, sealing into summaries, and tree hierarchy.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional, List

from models import Job, JobKind, TreeType
from config import BUFFER_SEAL_THRESHOLD, GROQ_API_KEY, GROQ_MODEL, GROQ_API_URL
import db


def append_chunk_to_source_tree(conn: sqlite3.Connection, chunk_id: str, source_id: str):
    """Add a chunk to its source tree's L0 buffer. Enqueue seal if threshold reached."""
    buffer = db.get_buffer(conn, TreeType.SOURCE.value, source_id, level=0)
    new_count = db.append_to_buffer(conn, buffer["buffer_id"], chunk_id)
    db.update_chunk_status(conn, chunk_id, db.LifecycleStatus.BUFFERED)

    if new_count >= BUFFER_SEAL_THRESHOLD:
        job = Job(
            kind=JobKind.SEAL,
            payload={"buffer_id": buffer["buffer_id"], "tree_type": "source", "tree_key": source_id, "level": 0},
            dedupe_key=f"seal:{buffer['buffer_id']}"
        )
        db.enqueue_job(conn, job)
    conn.commit()


def seal_buffer(conn: sqlite3.Connection, buffer_id: str, tree_type: str,
                tree_key: str, level: int):
    """Seal a buffer: summarize its chunks into an L(n+1) node.

    Uses Groq LLM to generate summary, then creates a tree node and summary record.
    """
    import os
    from urllib.request import Request, urlopen

    row = conn.execute(
        "SELECT * FROM mem_tree_buffers WHERE buffer_id = ?", (buffer_id,)
    ).fetchone()
    if not row:
        return

    chunk_ids = json.loads(row["chunk_ids_json"])
    if not chunk_ids:
        return

    # Gather chunk contents
    placeholders = ",".join("?" * len(chunk_ids))
    chunks = conn.execute(
        f"SELECT chunk_id, content FROM mem_tree_chunks WHERE chunk_id IN ({placeholders})",
        chunk_ids
    ).fetchall()

    combined = "\n\n---\n\n".join(c["content"] for c in chunks)

    # Generate summary via LLM
    summary_text = _generate_summary(combined, tree_key, level)

    # Create tree node
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    node_id = f"{tree_type}:{tree_key}:L{level+1}:{now}:{row['chunk_count']}"

    conn.execute(
        """INSERT OR IGNORE INTO mem_tree_trees (node_id, tree_type, tree_key, level)
           VALUES (?, ?, ?, ?)""",
        (node_id, tree_type, tree_key, level + 1)
    )

    # Create summary
    summary_id = f"summary:{node_id}"
    entity_ids = []
    # Collect entity IDs from chunks
    for cid in chunk_ids:
        rows = conn.execute(
            "SELECT entity_id FROM mem_tree_entity_chunks WHERE chunk_id = ?", (cid,)
        ).fetchall()
        entity_ids.extend(r["entity_id"] for r in rows)

    conn.execute(
        """INSERT OR REPLACE INTO mem_tree_summaries
           (summary_id, node_id, content, source_chunk_ids_json, entity_ids_json, token_count)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (summary_id, node_id, summary_text, json.dumps(chunk_ids),
         json.dumps(list(set(entity_ids))), len(summary_text) // 4)
    )

    # Mark chunks as sealed
    for cid in chunk_ids:
        db.update_chunk_status(conn, cid, db.LifecycleStatus.SEALED)

    # Reset buffer
    conn.execute(
        """UPDATE mem_tree_buffers
           SET chunk_ids_json = '[]', chunk_count = 0,
               updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
           WHERE buffer_id = ?""",
        (buffer_id,)
    )
    conn.commit()


def _generate_summary(content: str, context: str, level: int) -> str:
    """Generate a summary using Anthropic (primary) or Groq (fallback)."""
    import os
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    prompt = f"""Summarize the following content into a concise, informative summary.
Preserve all named entities, key facts, dates, and relationships.
Context: This is from the "{context}" source at tree level {level}.

CONTENT:
{content[:6000]}

Write a clear summary in 2-4 paragraphs. Preserve specific names, numbers, and facts."""

    # Try Anthropic first
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            from config import ANTHROPIC_MODEL, ANTHROPIC_API_URL
            payload = json.dumps({
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1000,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
            }).encode("utf-8")
            req = Request(ANTHROPIC_API_URL, data=payload, headers={
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }, method="POST")
            with urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
                return result["content"][0]["text"]
        except Exception:
            pass  # Fall through to Groq

    # Groq fallback
    api_key = GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return f"[Auto-summary of {context} L{level}]\n\n" + content[:500] + "..."

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise summarizer. Preserve facts and entities."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1000
    }).encode("utf-8")

    try:
        req = Request(GROQ_API_URL, data=payload, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, method="POST")
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result["choices"][0]["message"]["content"]
    except Exception:
        return f"[Auto-summary of {context} L{level}]\n\n" + content[:500] + "..."


def route_to_topic_tree(conn: sqlite3.Connection, chunk_id: str, entities: list):
    """Route admitted entities to topic trees if they're hot enough."""
    HOTNESS_THRESHOLD = 3.0  # minimum hotness to get a topic tree

    for entity in entities:
        row = conn.execute(
            "SELECT entity_id, hotness FROM mem_tree_entity_index WHERE name = ?",
            (entity.name,)
        ).fetchone()
        if row and row["hotness"] >= HOTNESS_THRESHOLD:
            buffer = db.get_buffer(conn, TreeType.TOPIC.value, entity.name, level=0)
            db.append_to_buffer(conn, buffer["buffer_id"], chunk_id)
    conn.commit()
