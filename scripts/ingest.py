"""Stage 1: Hot path ingestion for Memory Tree Pipeline.

Takes a Document, canonicalizes it, chunks it, fast-scores each chunk,
persists chunks + scores, and enqueues extract_chunk jobs.
"""
from typing import Dict
import sqlite3

from models import Chunk, Job, JobKind, LifecycleStatus, Document
from chunker import chunk_markdown, estimate_tokens
from scorer import fast_score
from config import FAST_SCORE_DROP_THRESHOLD
import db


def ingest_document(conn: sqlite3.Connection, doc: Document) -> Dict:
    """Ingest a document into the Memory Tree pipeline.

    Returns dict with stats: chunks_created, chunks_skipped, jobs_enqueued
    """
    chunks_created = 0
    chunks_skipped = 0
    jobs_enqueued = 0

    # Chunk the document
    raw_chunks = chunk_markdown(doc.content)

    for raw in raw_chunks:
        chunk_id = Chunk.make_id(raw)

        # Check for duplicate
        existing = conn.execute(
            "SELECT chunk_id FROM mem_tree_chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        if existing:
            chunks_skipped += 1
            continue

        # Create chunk
        chunk = Chunk(
            chunk_id=chunk_id,
            source_id=doc.source_id,
            source_path=doc.source_path,
            content=raw,
            token_count=estimate_tokens(raw),
            lifecycle_status=LifecycleStatus.PENDING_EXTRACTION
        )

        # Fast score
        score = fast_score(chunk_id, raw, source_id=doc.source_id)

        # Persist atomically
        db.insert_chunk(conn, chunk)
        db.insert_score(conn, score)

        # Drop low-quality chunks immediately
        if score.fast_score < FAST_SCORE_DROP_THRESHOLD:
            db.update_chunk_status(conn, chunk_id, LifecycleStatus.DROPPED)
            chunks_created += 1
            continue

        # Enqueue extraction job
        job = Job(
            kind=JobKind.EXTRACT_CHUNK,
            payload={"chunk_id": chunk_id},
            dedupe_key=f"extract:{chunk_id}"
        )
        db.enqueue_job(conn, job)
        jobs_enqueued += 1
        chunks_created += 1

    conn.commit()

    return {
        "chunks_created": chunks_created,
        "chunks_skipped": chunks_skipped,
        "jobs_enqueued": jobs_enqueued,
        "source_id": doc.source_id,
        "source_path": doc.source_path
    }
