#!/usr/bin/env python3
"""Maintenance tasks for Memory Tree Pipeline.

Usage:
    python3 maintenance.py dedup        # Deduplicate entities
    python3 maintenance.py hotness      # Recompute hotness scores
    python3 maintenance.py fix-buffers  # Move admitted chunks into buffers
    python3 maintenance.py all          # Run all maintenance
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from models import LifecycleStatus


def dedup_entities():
    """Merge duplicate entities."""
    conn = db.get_connection()
    merged = db.entity_dedup(conn)
    conn.close()
    print(f"[maintenance] Merged {merged} duplicate entities")


def recompute_hotness():
    """Recompute hotness scores for all entities."""
    conn = db.get_connection()
    updated = db.recompute_hotness(conn)
    conn.close()
    print(f"[maintenance] Updated hotness for {updated} entities")


def fix_buffers():
    """Move admitted chunks into source tree buffers."""
    conn = db.get_connection()
    from trees import append_chunk_to_source_tree

    rows = conn.execute(
        """SELECT chunk_id, source_id FROM mem_tree_chunks
           WHERE lifecycle_status = 'admitted'
           ORDER BY created_at"""
    ).fetchall()

    moved = 0
    for row in rows:
        try:
            append_chunk_to_source_tree(conn, row["chunk_id"], row["source_id"])
            moved += 1
        except Exception as e:
            print(f"  Error buffering {row['chunk_id']}: {e}")

    conn.commit()
    conn.close()
    print(f"[maintenance] Moved {moved} chunks into buffers")


def run_all():
    db.init_db()
    dedup_entities()
    recompute_hotness()
    fix_buffers()


def main():
    db.init_db()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "dedup":
        dedup_entities()
    elif cmd == "hotness":
        recompute_hotness()
    elif cmd == "fix-buffers":
        fix_buffers()
    elif cmd == "all":
        run_all()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
