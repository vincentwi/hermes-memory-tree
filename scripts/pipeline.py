#!/usr/bin/env python3
"""Memory Tree Pipeline — main entry point.

Usage:
    python3 pipeline.py ingest <source_id> <path>   # Ingest a single file
    python3 pipeline.py workers                       # Run worker pool
    python3 pipeline.py stats                         # Show pipeline stats
    python3 pipeline.py digest                        # Trigger daily digest
    python3 pipeline.py flush                         # Flush stale buffers
"""
import sys
import os
import json

# Ensure scripts dir is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from models import Document, Job, JobKind
from ingest import ingest_document


def cmd_ingest(source_id: str, path: str):
    """Ingest a single file."""
    db.init_db()
    conn = db.get_connection()

    with open(path) as f:
        content = f.read()

    doc = Document(
        source_id=source_id,
        source_path=path,
        content=content,
        title=os.path.basename(path)
    )
    result = ingest_document(conn, doc)
    conn.close()
    print(json.dumps(result, indent=2))


def cmd_workers():
    """Run the worker pool."""
    db.init_db()
    from workers import run_workers
    run_workers()


def cmd_stats():
    """Show pipeline statistics."""
    db.init_db()
    conn = db.get_connection()
    stats = db.get_stats(conn)
    conn.close()
    print(json.dumps(stats, indent=2))


def cmd_digest():
    """Trigger a daily digest job."""
    db.init_db()
    conn = db.get_connection()
    import time
    job = Job(
        kind=JobKind.DIGEST_DAILY,
        payload={"date": time.strftime("%Y-%m-%d")},
        dedupe_key=f"digest:{time.strftime('%Y-%m-%d')}"
    )
    job_id = db.enqueue_job(conn, job)
    conn.commit()
    conn.close()
    print(f"Enqueued digest job {job_id}")


def cmd_flush():
    """Trigger a flush_stale job."""
    db.init_db()
    conn = db.get_connection()
    job = Job(kind=JobKind.FLUSH_STALE, payload={})
    job_id = db.enqueue_job(conn, job)
    conn.commit()
    conn.close()
    print(f"Enqueued flush job {job_id}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "ingest" and len(sys.argv) >= 4:
        cmd_ingest(sys.argv[2], sys.argv[3])
    elif cmd == "workers":
        cmd_workers()
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "digest":
        cmd_digest()
    elif cmd == "flush":
        cmd_flush()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
