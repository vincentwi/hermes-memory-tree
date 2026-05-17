#!/usr/bin/env python3
"""Bidirectional sync engine — pushes Memory Tree entities to Wiki, Obsidian, TheBrain, Memory Graph.

Usage:
    python3 sync.py push-graph      # Push entities/relations to Hermes Memory Graph
    python3 sync.py push-obsidian   # Write entity summaries to Obsidian vault
    python3 sync.py push-wiki       # Write entity pages to LLM Wiki
    python3 sync.py push-brain      # Push entities to TheBrain
    python3 sync.py push-all        # Push to all targets
"""
import sys
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from config import (
    OBSIDIAN_VAULT, LLM_WIKI,
    THEBRAIN_API, THEBRAIN_BRAIN_ID, THEBRAIN_API_KEY, THEBRAIN_HOME_THOUGHT,
    MEMORY_TREE_DIR
)


def push_to_memory_graph():
    """Push entities and relations to Hermes Memory Graph MCP.

    Since we can't call MCP directly from a script, we write a JSON file
    that Hermes can read and execute as MCP calls.
    """
    conn = db.get_connection()

    entities = conn.execute(
        "SELECT * FROM mem_tree_entity_index ORDER BY hotness DESC LIMIT 200"
    ).fetchall()

    relations = conn.execute(
        "SELECT * FROM mem_tree_relations ORDER BY created_at DESC LIMIT 500"
    ).fetchall()

    # Write MCP commands as JSON for Hermes to execute
    mcp_commands = {
        "entities": [
            {
                "name": e["name"],
                "entityType": e["entity_type"],
                "observations": []
            }
            for e in entities
        ],
        "relations": [
            {
                "from": r["subject"],
                "relationType": r["predicate"],
                "to": r["object"]
            }
            for r in relations
        ]
    }

    # Add observations from chunks
    for i, entity in enumerate(entities):
        chunks = conn.execute(
            """SELECT c.content FROM mem_tree_chunks c
               JOIN mem_tree_entity_chunks ec ON c.chunk_id = ec.chunk_id
               WHERE ec.entity_id = ?
               ORDER BY c.created_at DESC LIMIT 3""",
            (entity["entity_id"],)
        ).fetchall()
        observations = [c["content"][:200] for c in chunks]
        if observations:
            mcp_commands["entities"][i]["observations"] = observations

    output_path = MEMORY_TREE_DIR / "memory_graph_sync.json"
    output_path.write_text(json.dumps(mcp_commands, indent=2))
    conn.close()
    print(f"[sync] Wrote {len(mcp_commands['entities'])} entities, {len(mcp_commands['relations'])} relations to {output_path}")
    print("[sync] Run: hermes can execute these via mcp_memory_graph_create_entities/create_relations")


def push_to_obsidian():
    """Write entity summary pages to Obsidian vault."""
    conn = db.get_connection()
    output_dir = OBSIDIAN_VAULT / "Memory Tree"
    output_dir.mkdir(exist_ok=True)

    entities = conn.execute(
        "SELECT * FROM mem_tree_entity_index WHERE hotness > 1.0 ORDER BY hotness DESC LIMIT 200"
    ).fetchall()

    written = 0
    for entity in entities:
        # Get summaries mentioning this entity
        summaries = conn.execute(
            """SELECT s.content FROM mem_tree_summaries s
               WHERE s.entity_ids_json LIKE ?
               ORDER BY s.created_at DESC LIMIT 5""",
            (f"%{entity['entity_id']}%",)
        ).fetchall()

        # Get relations
        relations = conn.execute(
            """SELECT predicate, object FROM mem_tree_relations WHERE subject = ?
               UNION
               SELECT predicate, subject FROM mem_tree_relations WHERE object = ?""",
            (entity["name"], entity["name"])
        ).fetchall()

        # Build page
        lines = [
            "---",
            f"title: {entity['name']}",
            f"type: {entity['entity_type']}",
            f"hotness: {entity['hotness']}",
            f"mentions: {entity['mention_count']}",
            f"auto_generated: true",
            f"updated: {datetime.now().strftime('%Y-%m-%d')}",
            "---",
            f"# {entity['name']}",
            f"Type: {entity['entity_type']} | Mentions: {entity['mention_count']} | Hotness: {entity['hotness']:.1f}",
            ""
        ]

        if relations:
            lines.append("## Connections")
            for r in relations:
                lines.append(f"- {r['predicate']} [[{r['object']}]]" if 'object' in r.keys() else f"- {r['predicate']}")
            lines.append("")

        if summaries:
            lines.append("## Summaries")
            for s in summaries:
                lines.append(s["content"][:500])
                lines.append("")

        # Write file
        safe_name = entity["name"].replace("/", "-").replace("\\", "-")
        file_path = output_dir / f"{safe_name}.md"
        file_path.write_text("\n".join(lines))
        written += 1

    conn.close()
    print(f"[sync] Wrote {written} entity pages to {output_dir}")


def push_to_wiki():
    """Write entity pages to LLM Wiki."""
    conn = db.get_connection()
    entities_dir = LLM_WIKI / "entities"
    entities_dir.mkdir(exist_ok=True)

    entities = conn.execute(
        "SELECT * FROM mem_tree_entity_index WHERE hotness > 1.0 ORDER BY hotness DESC LIMIT 100"
    ).fetchall()

    written = 0
    for entity in entities:
        safe_name = entity["name"].lower().replace(" ", "-").replace("/", "-")
        file_path = entities_dir / f"{safe_name}.md"

        # Skip if already exists and was manually maintained
        if file_path.exists():
            content = file_path.read_text()
            if "auto_generated: true" not in content:
                continue  # Don't overwrite manual pages

        # Get context
        chunks = conn.execute(
            """SELECT c.content FROM mem_tree_chunks c
               JOIN mem_tree_entity_chunks ec ON c.chunk_id = ec.chunk_id
               WHERE ec.entity_id = ?
               ORDER BY c.created_at DESC LIMIT 5""",
            (entity["entity_id"],)
        ).fetchall()

        lines = [
            "---",
            f"title: {entity['name']}",
            f"created: {entity['first_seen'][:10]}",
            f"updated: {datetime.now().strftime('%Y-%m-%d')}",
            f"type: entity",
            f"tags: [{entity['entity_type']}]",
            f"auto_generated: true",
            "---",
            f"# {entity['name']}",
            "",
        ]

        if chunks:
            lines.append("## Context")
            for c in chunks:
                lines.append(c["content"][:300])
                lines.append("")

        file_path.write_text("\n".join(lines))
        written += 1

    conn.close()
    print(f"[sync] Wrote {written} entity pages to {entities_dir}")


def push_to_brain():
    """Push hot entities to TheBrain as new thoughts."""
    if not THEBRAIN_API_KEY:
        print("[sync] TheBrain API key not set, skipping")
        return

    conn = db.get_connection()
    entities = conn.execute(
        "SELECT * FROM mem_tree_entity_index WHERE hotness > 3.0 ORDER BY hotness DESC LIMIT 100"
    ).fetchall()

    created = 0
    for entity in entities:
        try:
            # TheBrain API: POST /thoughts/{brainId} with sourceThoughtId for parent link
            payload = json.dumps({
                "name": entity["name"],
                "kind": 1,  # Normal thought
                "acType": 0,
                "sourceThoughtId": THEBRAIN_HOME_THOUGHT,
                "relation": 1  # child relation
            }).encode("utf-8")

            req = Request(
                f"{THEBRAIN_API}/thoughts/{THEBRAIN_BRAIN_ID}",
                data=payload,
                headers={
                    "Authorization": f"Bearer {THEBRAIN_API_KEY}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                created += 1
            time.sleep(2.0)  # Rate limit
        except URLError as e:
            if "409" in str(e) or "already exists" in str(e).lower():
                pass  # Thought already exists
            else:
                print(f"[sync] Failed to create thought '{entity['name']}': {e}")

    conn.close()
    print(f"[sync] Created {created} thoughts in TheBrain")


def push_all():
    """Push to all targets."""
    push_to_memory_graph()
    push_to_obsidian()
    push_to_wiki()
    push_to_brain()


def main():
    db.init_db()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    cmds = {
        "push-graph": push_to_memory_graph,
        "push-obsidian": push_to_obsidian,
        "push-wiki": push_to_wiki,
        "push-brain": push_to_brain,
        "push-all": push_all,
    }
    if cmd in cmds:
        cmds[cmd]()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
