#!/usr/bin/env python3
"""agentmemory REST bridge — syncs Memory Tree entities/relations to agentmemory daemon.

This enables Claude Code, Cursor, Codex, and other AI tools to share memory.

Usage:
    python3 agentmemory_bridge.py sync     # Sync entities to agentmemory
    python3 agentmemory_bridge.py health   # Check agentmemory health
    python3 agentmemory_bridge.py query <text>  # Search agentmemory
"""
import sys
import os
import json
from urllib.request import Request, urlopen
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from config import AGENTMEMORY_URL


def _post(endpoint: str, data: dict) -> dict:
    """POST to agentmemory API."""
    url = f"{AGENTMEMORY_URL}/{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _get(endpoint: str) -> dict:
    """GET from agentmemory API."""
    url = f"{AGENTMEMORY_URL}/{endpoint}"
    req = Request(url, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def health_check() -> bool:
    """Check if agentmemory is running."""
    try:
        result = _get("agentmemory/livez")
        return True
    except Exception:
        return False


def sync_entities_to_agentmemory():
    """Push all entities and their latest context to agentmemory."""
    if not health_check():
        print("[agentmemory] Daemon not running at", AGENTMEMORY_URL)
        print("Start with: npx -y @agentmemory/agentmemory")
        return

    conn = db.get_connection()

    # Get all entities
    entities = conn.execute(
        "SELECT * FROM mem_tree_entity_index ORDER BY hotness DESC"
    ).fetchall()

    synced = 0
    for entity in entities:
        # Get related chunks for context
        chunks = conn.execute(
            """SELECT c.content FROM mem_tree_chunks c
               JOIN mem_tree_entity_chunks ec ON c.chunk_id = ec.chunk_id
               WHERE ec.entity_id = ?
               ORDER BY c.created_at DESC LIMIT 3""",
            (entity["entity_id"],)
        ).fetchall()

        context = "\n---\n".join(c["content"][:500] for c in chunks)

        # Get relations
        relations = conn.execute(
            """SELECT predicate, object FROM mem_tree_relations
               WHERE subject = ? LIMIT 10""",
            (entity["name"],)
        ).fetchall()

        concepts = [f"{r['predicate']} {r['object']}" for r in relations]

        try:
            _post("agentmemory/remember", {
                "title": entity["name"],
                "content": context[:2000] if context else f"Entity: {entity['name']} ({entity['entity_type']})",
                "type": "fact",
                "project": "hermes-memory-tree",
                "concepts": concepts[:5]
            })
            synced += 1
        except URLError as e:
            print(f"[agentmemory] Failed to sync {entity['name']}: {e}")

    conn.close()
    print(f"[agentmemory] Synced {synced}/{len(entities)} entities")


def query_agentmemory(query: str) -> list:
    """Search agentmemory for relevant memories."""
    try:
        result = _post("agentmemory/smart-search", {
            "query": query,
            "project": "hermes-memory-tree",
            "limit": 10
        })
        return result.get("memories", result.get("results", []))
    except URLError as e:
        print(f"[agentmemory] Query failed: {e}")
        return []


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "sync":
        db.init_db()
        sync_entities_to_agentmemory()
    elif cmd == "health":
        print("OK" if health_check() else "UNAVAILABLE")
    elif cmd == "query" and len(sys.argv) >= 3:
        results = query_agentmemory(" ".join(sys.argv[2:]))
        print(json.dumps(results, indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
