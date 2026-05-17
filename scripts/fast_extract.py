#!/usr/bin/env python3
"""Fast parallel extraction — processes pending chunks directly with threading.
Bypasses the job queue for speed. Safe to run alongside workers (uses atomic status updates).
"""
import sys, os, json, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
from models import LifecycleStatus, Entity, EntityType
from extractor import extract_entities_llm
from trees import append_chunk_to_source_tree

db.init_db()
MAX_WORKERS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
BATCH_SIZE = int(sys.argv[2]) if len(sys.argv) > 2 else 200

lock = threading.Lock()
stats = {"processed": 0, "admitted": 0, "dropped": 0, "entities": 0, "relations": 0, "errors": 0}

def process_chunk(chunk_id, content, source_id):
    """Extract entities from a single chunk."""
    try:
        entities, relations, quality = extract_entities_llm(content)
        
        with lock:
            conn = db.get_connection()
            # Check it hasn't been claimed by another worker
            row = conn.execute(
                "SELECT lifecycle_status FROM mem_tree_chunks WHERE chunk_id = ?", (chunk_id,)
            ).fetchone()
            if row and row["lifecycle_status"] != "pending_extraction":
                conn.close()
                return  # Already processed by queue worker
            
            if quality < 0.3:
                db.update_chunk_status(conn, chunk_id, LifecycleStatus.DROPPED)
                stats["dropped"] += 1
            else:
                db.update_chunk_status(conn, chunk_id, LifecycleStatus.ADMITTED)
                for entity in entities:
                    eid = db.upsert_entity(conn, entity)
                    db.link_entity_chunk(conn, eid, chunk_id)
                for rel in relations:
                    rel.chunk_id = chunk_id
                    db.upsert_relation(conn, rel)
                conn.execute(
                    "UPDATE mem_tree_scores SET llm_score = ?, entity_count = ? WHERE chunk_id = ?",
                    (quality, len(entities), chunk_id)
                )
                # Inline buffer append
                try:
                    append_chunk_to_source_tree(conn, chunk_id, source_id)
                except Exception:
                    pass
                stats["admitted"] += 1
                stats["entities"] += len(entities)
                stats["relations"] += len(relations)
            
            conn.commit()
            conn.close()
            stats["processed"] += 1
            
            if stats["processed"] % 10 == 0:
                print(f"  [{stats['processed']}] +{stats['entities']}e +{stats['relations']}r | {stats['admitted']} admitted, {stats['dropped']} dropped, {stats['errors']} errors")
    except Exception as e:
        with lock:
            stats["errors"] += 1

# Grab pending chunks
conn = db.get_connection()
pending = conn.execute(
    """SELECT chunk_id, content, source_id FROM mem_tree_chunks 
       WHERE lifecycle_status = 'pending_extraction' 
       ORDER BY RANDOM() LIMIT ?""",
    (BATCH_SIZE,)
).fetchall()
conn.close()

print(f"[fast-extract] Processing {len(pending)} chunks with {MAX_WORKERS} threads...")
start = time.time()

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {
        executor.submit(process_chunk, r["chunk_id"], r["content"], r["source_id"]): r["chunk_id"]
        for r in pending
    }
    for f in as_completed(futures):
        pass  # Results handled in process_chunk

elapsed = time.time() - start
print(f"\n[fast-extract] Done in {elapsed:.1f}s")
print(f"  Processed: {stats['processed']}")
print(f"  Admitted: {stats['admitted']}, Dropped: {stats['dropped']}, Errors: {stats['errors']}")
print(f"  New entities: {stats['entities']}, New relations: {stats['relations']}")
print(f"  Rate: {stats['processed']/max(elapsed,1):.1f} chunks/sec")
