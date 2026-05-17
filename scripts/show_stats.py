#!/usr/bin/env python3
"""Show pipeline stats after maintenance."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
db.init_db()
conn = db.get_connection()

print("=== ENTITY STATS ===")
cnt = conn.execute("SELECT COUNT(*) FROM mem_tree_entity_index").fetchone()[0]
print("Total entities:", cnt)
print()

print("Top 15 by hotness:")
rows = conn.execute("SELECT name, mention_count, hotness, entity_type FROM mem_tree_entity_index ORDER BY hotness DESC LIMIT 15").fetchall()
for r in rows:
    print("  %8.1f | %4dx | %10s | %s" % (r[2], r[1], r[3], r[0]))

print()
print("=== BUFFER STATS ===")
brows = conn.execute("SELECT buffer_id, chunk_count, max_chunks FROM mem_tree_buffers WHERE chunk_count > 0").fetchall()
for r in brows:
    print("  %s  %d/%d chunks" % (r[0], r[1], r[2]))
if not brows:
    print("  (no active buffers)")

print()
print("=== CHUNK LIFECYCLE ===")
for row in conn.execute("SELECT lifecycle_status, COUNT(*) as cnt FROM mem_tree_chunks GROUP BY lifecycle_status ORDER BY cnt DESC").fetchall():
    print("  %20s: %d" % (row[0], row[1]))

print()
from config import WORKER_COUNT, LLM_CONCURRENCY
print("Config: WORKER_COUNT=%d, LLM_CONCURRENCY=%d" % (WORKER_COUNT, LLM_CONCURRENCY))
conn.close()
