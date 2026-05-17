"""Tests for the ingestion pipeline."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import db
from ingest import ingest_document
from models import Document


def setup():
    tmp = tempfile.mkdtemp()
    db.DB_DIR = Path(tmp)
    db.DB_PATH = Path(tmp) / "test.db"
    db.init_db()
    return db.get_connection()


def test_ingest_creates_chunks_and_jobs():
    conn = setup()
    doc = Document(
        source_id="wiki",
        source_path="test.md",
        content="# Test Document\n\nThis is a test about Vincent W working at Nous Research in San Francisco.\n\n## Section 2\n\nMore content about AI and machine learning projects."
    )
    result = ingest_document(conn, doc)
    assert result["chunks_created"] >= 1
    assert result["jobs_enqueued"] >= 1

    # Check chunks exist
    row = conn.execute("SELECT COUNT(*) as cnt FROM mem_tree_chunks").fetchone()
    assert row["cnt"] >= 1

    # Check jobs exist
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM mem_tree_jobs WHERE kind = 'extract_chunk'"
    ).fetchone()
    assert row["cnt"] >= 1
    conn.close()


def test_ingest_deduplicates():
    conn = setup()
    doc = Document(source_id="wiki", source_path="test.md", content="Hello world test content")
    r1 = ingest_document(conn, doc)
    r2 = ingest_document(conn, doc)
    assert r1["chunks_created"] >= 1
    assert r2["chunks_created"] == 0  # duplicate, no new chunks
    conn.close()


if __name__ == "__main__":
    test_ingest_creates_chunks_and_jobs()
    test_ingest_deduplicates()
    print("All ingest tests passed!")
