"""Tests for the database layer."""
import sys
import os
import sqlite3
import tempfile
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import db
from models import Chunk, Score, Entity, Job, JobKind, EntityType, LifecycleStatus


def setup_test_db():
    """Create a temporary test database."""
    tmp = tempfile.mkdtemp()
    db.DB_DIR = Path(tmp)
    db.DB_PATH = Path(tmp) / "test_chunks.db"
    db.init_db()
    return db.get_connection()


def test_init_db():
    conn = setup_test_db()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "mem_tree_chunks" in tables
    assert "mem_tree_jobs" in tables
    assert "mem_tree_entity_index" in tables
    conn.close()


def test_insert_and_query_chunk():
    conn = setup_test_db()
    chunk = Chunk(
        chunk_id="abc123", source_id="wiki",
        source_path="test.md", content="Hello world",
        token_count=2
    )
    db.insert_chunk(conn, chunk)
    conn.commit()
    row = conn.execute("SELECT * FROM mem_tree_chunks WHERE chunk_id = 'abc123'").fetchone()
    assert row is not None
    assert row["source_id"] == "wiki"
    assert row["lifecycle_status"] == "pending_extraction"
    conn.close()


def test_enqueue_and_claim_job():
    conn = setup_test_db()
    job = Job(kind=JobKind.EXTRACT_CHUNK, payload={"chunk_id": "abc123"})
    job_id = db.enqueue_job(conn, job)
    conn.commit()
    claimed = db.claim_job(conn)
    conn.commit()
    assert claimed is not None
    assert claimed["kind"] == "extract_chunk"
    # No more jobs
    assert db.claim_job(conn) is None
    conn.close()


def test_entity_upsert():
    conn = setup_test_db()
    e = Entity(name="Vincent", entity_type=EntityType.PERSON)
    eid1 = db.upsert_entity(conn, e)
    eid2 = db.upsert_entity(conn, e)
    conn.commit()
    assert eid1 == eid2
    row = conn.execute(
        "SELECT mention_count FROM mem_tree_entity_index WHERE entity_id = ?", (eid1,)
    ).fetchone()
    assert row["mention_count"] == 2
    conn.close()


if __name__ == "__main__":
    test_init_db()
    test_insert_and_query_chunk()
    test_enqueue_and_claim_job()
    test_entity_upsert()
    print("All db tests passed!")
