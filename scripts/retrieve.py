#!/usr/bin/env python3
"""Memory Tree retrieval API — search, drill-down, topic browsing.

Usage:
    python3 retrieve.py search <query> [--namespace=<ns>] [--limit=10]
    python3 retrieve.py drill <summary_id>
    python3 retrieve.py topic <entity_name>
    python3 retrieve.py digest [<date>]  # defaults to today
    python3 retrieve.py status           # pipeline health
    python3 retrieve.py report [--limit=50]  # entity report with source traceability
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db


def search(query: str, namespace: str = None, limit: int = 10) -> list:
    """Search chunks and summaries by text content."""
    db.init_db()
    conn = db.get_connection()
    params = [f"%{query}%"]
    where = "WHERE c.content LIKE ?"
    if namespace:
        where += " AND c.source_id = ?"
        params.append(namespace)
    rows = conn.execute(
        f"""SELECT c.chunk_id, c.source_id, c.source_path, c.content,
                   s.fast_score, c.lifecycle_status, c.created_at
            FROM mem_tree_chunks c
            LEFT JOIN mem_tree_scores s ON c.chunk_id = s.chunk_id
            {where}
            ORDER BY s.fast_score DESC NULLS LAST
            LIMIT ?""",
        params + [limit]
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def drill_down(summary_id: str) -> dict:
    """Expand a summary into its constituent chunks."""
    db.init_db()
    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM mem_tree_summaries WHERE summary_id = ?", (summary_id,)
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Summary not found"}
    chunk_ids = json.loads(row["source_chunk_ids_json"])
    chunks = []
    for cid in chunk_ids:
        c = conn.execute(
            "SELECT chunk_id, source_id, source_path, content FROM mem_tree_chunks WHERE chunk_id = ?",
            (cid,)
        ).fetchone()
        if c:
            chunks.append(dict(c))
    conn.close()
    return {"summary": dict(row), "chunks": chunks}


def topic(entity_name: str) -> dict:
    """Get all chunks and summaries mentioning an entity."""
    db.init_db()
    conn = db.get_connection()
    entity = conn.execute(
        "SELECT * FROM mem_tree_entity_index WHERE name = ?", (entity_name,)
    ).fetchone()
    if not entity:
        conn.close()
        return {"error": f"Entity '{entity_name}' not found"}
    chunks = conn.execute(
        """SELECT c.chunk_id, c.source_id, c.source_path, c.content, c.created_at
           FROM mem_tree_chunks c
           JOIN mem_tree_entity_chunks ec ON c.chunk_id = ec.chunk_id
           WHERE ec.entity_id = ?
           ORDER BY c.created_at DESC""",
        (entity["entity_id"],)
    ).fetchall()
    relations = conn.execute(
        """SELECT predicate, object, confidence FROM mem_tree_relations WHERE subject = ?
           UNION
           SELECT predicate, subject, confidence FROM mem_tree_relations WHERE object = ?""",
        (entity_name, entity_name)
    ).fetchall()
    conn.close()
    return {
        "entity": dict(entity),
        "chunks": [dict(c) for c in chunks],
        "relations": [dict(r) for r in relations]
    }


def global_digest(date: str = None) -> dict:
    """Get the global daily digest for a date."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    db.init_db()
    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM mem_tree_summaries WHERE summary_id = ?",
        (f"digest:{date}",)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"error": f"No digest found for {date}"}


def pipeline_status() -> dict:
    """Get full pipeline health report."""
    db.init_db()
    conn = db.get_connection()
    stats = db.get_stats(conn)
    # Add sync state
    sync_rows = conn.execute("SELECT * FROM mem_tree_sync_state").fetchall()
    stats["sync_state"] = {r["source_id"]: {
        "last_sync": r["last_sync_ts"],
        "failures": r["consecutive_failures"]
    } for r in sync_rows}
    # Add tree counts
    tree_count = conn.execute("SELECT COUNT(*) as cnt FROM mem_tree_trees").fetchone()
    stats["tree_nodes"] = tree_count["cnt"]
    summary_count = conn.execute("SELECT COUNT(*) as cnt FROM mem_tree_summaries").fetchone()
    stats["summaries"] = summary_count["cnt"]
    # Hot entities
    hot = conn.execute(
        "SELECT name, entity_type, hotness FROM mem_tree_entity_index ORDER BY hotness DESC LIMIT 10"
    ).fetchall()
    stats["hot_entities"] = [dict(e) for e in hot]
    conn.close()
    return stats


def entity_report(limit: int = 50) -> list:
    """Generate a rich entity report with source file traceability."""
    db.init_db()
    conn = db.get_connection()
    entities = conn.execute(
        '''SELECT entity_id, name, entity_type, mention_count, hotness, first_seen, last_seen
           FROM mem_tree_entity_index ORDER BY hotness DESC, mention_count DESC LIMIT ?''',
        (limit,)
    ).fetchall()

    report = []
    for e in entities:
        # Source files
        sources = conn.execute(
            '''SELECT DISTINCT c.source_id, c.source_path
               FROM mem_tree_chunks c
               JOIN mem_tree_entity_chunks ec ON c.chunk_id = ec.chunk_id
               WHERE ec.entity_id = ?
               ORDER BY c.source_id''',
            (e['entity_id'],)
        ).fetchall()

        # Relations out
        rels_out = conn.execute(
            'SELECT predicate, object FROM mem_tree_relations WHERE subject = ? LIMIT 10',
            (e['name'],)
        ).fetchall()
        # Relations in
        rels_in = conn.execute(
            'SELECT subject, predicate FROM mem_tree_relations WHERE object = ? LIMIT 10',
            (e['name'],)
        ).fetchall()

        # Best quote
        best_chunk = conn.execute(
            '''SELECT c.content, s.fast_score FROM mem_tree_chunks c
               JOIN mem_tree_entity_chunks ec ON c.chunk_id = ec.chunk_id
               JOIN mem_tree_scores s ON c.chunk_id = s.chunk_id
               WHERE ec.entity_id = ?
               ORDER BY s.fast_score DESC LIMIT 1''',
            (e['entity_id'],)
        ).fetchone()

        entry = {
            'name': e['name'],
            'type': e['entity_type'],
            'mentions': e['mention_count'],
            'hotness': e['hotness'],
            'first_seen': e['first_seen'],
            'last_seen': e['last_seen'],
            'source_files': [{'source': s['source_id'], 'path': s['source_path']} for s in sources],
            'relations_out': [{'predicate': r['predicate'], 'object': r['object']} for r in rels_out],
            'relations_in': [{'subject': r['subject'], 'predicate': r['predicate']} for r in rels_in],
            'sample_quote': best_chunk['content'][:300] if best_chunk else None,
        }
        report.append(entry)

    conn.close()
    return report


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "search" and len(sys.argv) >= 3:
        query = sys.argv[2]
        ns = None
        limit = 10
        for arg in sys.argv[3:]:
            if arg.startswith("--namespace="):
                ns = arg.split("=", 1)[1]
            elif arg.startswith("--limit="):
                limit = int(arg.split("=", 1)[1])
        print(json.dumps(search(query, ns, limit), indent=2, default=str))
    elif cmd == "drill" and len(sys.argv) >= 3:
        print(json.dumps(drill_down(sys.argv[2]), indent=2, default=str))
    elif cmd == "topic" and len(sys.argv) >= 3:
        print(json.dumps(topic(sys.argv[2]), indent=2, default=str))
    elif cmd == "digest":
        date = sys.argv[2] if len(sys.argv) >= 3 else None
        print(json.dumps(global_digest(date), indent=2, default=str))
    elif cmd == "status":
        print(json.dumps(pipeline_status(), indent=2, default=str))
    elif cmd == "report":
        limit = 50
        for arg in sys.argv[2:]:
            if arg.startswith("--limit="):
                limit = int(arg.split("=", 1)[1])
        entries = entity_report(limit)
        for e in entries:
            print(f"\n{'='*70}")
            print(f"{e['name']} [{e['type']}] — {e['mentions']} mentions, hotness={e['hotness']:.1f}")
            print(f"First seen: {e['first_seen']}  Last seen: {e['last_seen']}")
            if e['source_files']:
                print(f"Source files ({len(e['source_files'])}):")
                for s in e['source_files']:
                    print(f"  [{s['source']}] {s['path']}")
            if e['relations_out']:
                print(f"Relations out:")
                for r in e['relations_out']:
                    print(f"  -> {r['predicate']} -> {r['object']}")
            if e['relations_in']:
                print(f"Relations in:")
                for r in e['relations_in']:
                    print(f"  {r['subject']} -> {r['predicate']} ->")
            if e['sample_quote']:
                print(f"Sample: {e['sample_quote'][:200]}...")
        print(f"\n{'='*70}")
        print(f"Total entities reported: {len(entries)}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
