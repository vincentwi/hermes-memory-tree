"""Stage 3: Async worker pool for processing Memory Tree jobs.

Runs N workers that claim jobs from the SQLite queue and process them.
Uses a semaphore to limit concurrent LLM calls.
"""
import json
import time
import threading
import signal
import sys
from typing import Callable, Dict

import db
from models import JobKind, LifecycleStatus, Entity, EntityType
from extractor import extract_entities_llm
from trees import append_chunk_to_source_tree, seal_buffer, route_to_topic_tree
from config import WORKER_COUNT, LLM_CONCURRENCY, FAST_SCORE_DROP_THRESHOLD


class WorkerPool:
    """Manages a pool of job-processing workers."""

    def __init__(self, num_workers: int = WORKER_COUNT, llm_semaphore_count: int = LLM_CONCURRENCY):
        self.num_workers = num_workers
        self.llm_semaphore = threading.Semaphore(llm_semaphore_count)
        self.running = True
        self.wake_event = threading.Event()
        self.workers = []
        self._handlers: Dict[str, Callable] = {
            JobKind.EXTRACT_CHUNK.value: self._handle_extract_chunk,
            JobKind.APPEND_BUFFER.value: self._handle_append_buffer,
            JobKind.SEAL.value: self._handle_seal,
            JobKind.TOPIC_ROUTE.value: self._handle_topic_route,
            JobKind.DIGEST_DAILY.value: self._handle_digest_daily,
            JobKind.FLUSH_STALE.value: self._handle_flush_stale,
        }

    def start(self):
        """Start the worker pool."""
        # Recover stale jobs first
        conn = db.get_connection()
        db.recover_stale_jobs(conn)
        conn.close()

        for i in range(self.num_workers):
            t = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            t.start()
            self.workers.append(t)

        print(f"[workers] Started {self.num_workers} workers")

    def stop(self):
        """Signal all workers to stop."""
        self.running = False
        self.wake_event.set()
        for t in self.workers:
            t.join(timeout=10)
        print("[workers] Stopped")

    def wake(self):
        """Wake workers to check for new jobs."""
        self.wake_event.set()

    def _worker_loop(self, worker_id: int):
        """Main loop for a single worker."""
        conn = db.get_connection()
        while self.running:
            job_row = db.claim_job(conn)
            conn.commit()

            if job_row is None:
                # Wait for wake signal or poll every 5s
                self.wake_event.wait(timeout=5.0)
                self.wake_event.clear()
                continue

            job_id = job_row["job_id"]
            kind = job_row["kind"]
            payload = json.loads(job_row["payload_json"])

            try:
                handler = self._handlers.get(kind)
                if handler:
                    handler(conn, payload)
                    db.complete_job(conn, job_id)
                else:
                    db.fail_job(conn, job_id, f"Unknown job kind: {kind}")
                conn.commit()
            except Exception as e:
                db.fail_job(conn, job_id, str(e)[:500])
                conn.commit()
                print(f"[worker-{worker_id}] Job {job_id} ({kind}) failed: {e}")

        conn.close()

    def _handle_extract_chunk(self, conn, payload):
        """Extract entities and relations from a chunk using LLM."""
        chunk_id = payload["chunk_id"]
        row = conn.execute(
            "SELECT content, source_id FROM mem_tree_chunks WHERE chunk_id = ?",
            (chunk_id,)
        ).fetchone()
        if not row:
            return

        # Use semaphore for LLM calls
        with self.llm_semaphore:
            entities, relations, quality = extract_entities_llm(row["content"])

        if quality < 0.3:
            db.update_chunk_status(conn, chunk_id, LifecycleStatus.DROPPED)
            return

        # Store entities and relations
        db.update_chunk_status(conn, chunk_id, LifecycleStatus.ADMITTED)
        for entity in entities:
            eid = db.upsert_entity(conn, entity)
            db.link_entity_chunk(conn, eid, chunk_id)
        for rel in relations:
            rel.chunk_id = chunk_id
            db.upsert_relation(conn, rel)

        # Update LLM score
        conn.execute(
            "UPDATE mem_tree_scores SET llm_score = ?, entity_count = ? WHERE chunk_id = ?",
            (quality, len(entities), chunk_id)
        )

        # Recompute hotness for entities we just touched
        if entities:
            db.recompute_hotness(conn)

        # Inline buffer append — directly add chunk to source tree buffer
        # (was previously a separate enqueued job that wasn't being processed reliably)
        try:
            append_chunk_to_source_tree(conn, chunk_id, row["source_id"])
        except Exception as e:
            print(f"[worker] Buffer append failed for {chunk_id}: {e}")

        if entities:
            db.enqueue_job(conn, db.Job(
                kind=JobKind.TOPIC_ROUTE,
                payload={"chunk_id": chunk_id, "entity_names": [e.name for e in entities]}
            ))
        conn.commit()
        self.wake()

    def _handle_append_buffer(self, conn, payload):
        """Append an admitted chunk to its source tree buffer."""
        append_chunk_to_source_tree(conn, payload["chunk_id"], payload["source_id"])
        self.wake()

    def _handle_seal(self, conn, payload):
        """Seal a buffer into a summary."""
        with self.llm_semaphore:
            seal_buffer(conn, payload["buffer_id"], payload["tree_type"],
                       payload["tree_key"], payload["level"])

    def _handle_topic_route(self, conn, payload):
        """Route chunks to topic trees."""
        from models import Entity, EntityType
        chunk_id = payload["chunk_id"]
        entities = []
        for name in payload.get("entity_names", []):
            entities.append(Entity(name=name, entity_type=EntityType.CONCEPT))
        route_to_topic_tree(conn, chunk_id, entities)

    def _handle_digest_daily(self, conn, payload):
        """Build a daily digest for the global tree."""
        date = payload.get("date", time.strftime("%Y-%m-%d"))
        # Gather all summaries created today
        rows = conn.execute(
            """SELECT content FROM mem_tree_summaries
               WHERE created_at LIKE ? ORDER BY created_at""",
            (f"{date}%",)
        ).fetchall()
        if not rows:
            return

        combined = "\n\n---\n\n".join(r["content"] for r in rows)
        from trees import _generate_summary
        with self.llm_semaphore:
            digest = _generate_summary(combined, "daily-digest", 0)

        node_id = f"global:daily:{date}"
        conn.execute(
            """INSERT OR IGNORE INTO mem_tree_trees (node_id, tree_type, tree_key, level)
               VALUES (?, 'global', 'daily', 1)""",
            (node_id,)
        )
        conn.execute(
            """INSERT OR REPLACE INTO mem_tree_summaries
               (summary_id, node_id, content, token_count)
               VALUES (?, ?, ?, ?)""",
            (f"digest:{date}", node_id, digest, len(digest) // 4)
        )
        conn.commit()

    def _handle_flush_stale(self, conn, payload):
        """Force-seal buffers that haven't been sealed in a while."""
        rows = conn.execute(
            """SELECT buffer_id, tree_type, tree_key, level, chunk_count
               FROM mem_tree_buffers
               WHERE chunk_count > 0
               AND updated_at < datetime('now', '-24 hours')"""
        ).fetchall()
        for row in rows:
            if row["chunk_count"] > 0:
                with self.llm_semaphore:
                    seal_buffer(conn, row["buffer_id"], row["tree_type"],
                               row["tree_key"], row["level"])


def run_workers():
    """Run the worker pool until interrupted."""
    pool = WorkerPool()
    pool.start()

    def shutdown(sig, frame):
        print("\n[workers] Shutting down...")
        pool.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep main thread alive
    while pool.running:
        time.sleep(1)


if __name__ == "__main__":
    db.init_db()
    run_workers()
