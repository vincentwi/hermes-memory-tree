#!/usr/bin/env python3
"""Auto-fetch scheduler — periodically pulls changes from all sources.

Usage:
    python3 auto_fetch.py           # Run one sync cycle
    python3 auto_fetch.py --loop    # Run continuously
"""
import sys
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from models import Document
from ingest import ingest_document
from config import (
    load_sync_state, save_sync_state,
    MEMORY_TREE_DIR, SYNC_INTERVAL_MINUTES
)
from providers import ALL_PROVIDERS


def run_sync_cycle() -> dict:
    """Run one sync cycle across all providers. Returns stats."""
    db.init_db()
    conn = db.get_connection()
    sync_state = load_sync_state()
    stats = {"sources": {}, "total_docs": 0, "total_chunks": 0}

    for ProviderClass in ALL_PROVIDERS:
        provider = ProviderClass()
        source_id = provider.source_id

        if not provider.health_check():
            stats["sources"][source_id] = {"status": "unavailable"}
            continue

        # Get last sync time
        last_sync = None
        if source_id in sync_state:
            try:
                last_sync = datetime.fromisoformat(sync_state[source_id]["last_sync_ts"])
            except (KeyError, ValueError):
                pass

        try:
            docs = provider.fetch_changes(since=last_sync)
            source_stats = {"docs_found": len(docs), "chunks_created": 0, "jobs_enqueued": 0}

            for doc in docs:
                result = ingest_document(conn, doc)
                source_stats["chunks_created"] += result["chunks_created"]
                source_stats["jobs_enqueued"] += result["jobs_enqueued"]

            # Update sync state
            sync_state[source_id] = {
                "last_sync_ts": datetime.now(timezone.utc).isoformat(),
                "consecutive_failures": 0,
                "last_error": None
            }
            source_stats["status"] = "ok"
            stats["sources"][source_id] = source_stats
            stats["total_docs"] += len(docs)
            stats["total_chunks"] += source_stats["chunks_created"]

        except Exception as e:
            failures = sync_state.get(source_id, {}).get("consecutive_failures", 0) + 1
            sync_state[source_id] = {
                "last_sync_ts": sync_state.get(source_id, {}).get("last_sync_ts"),
                "consecutive_failures": failures,
                "last_error": str(e)[:200]
            }
            stats["sources"][source_id] = {"status": "error", "error": str(e)[:200]}
            print(f"[auto-fetch] Error syncing {source_id}: {e}")

    save_sync_state(sync_state)
    conn.close()

    # Log results
    log_path = MEMORY_TREE_DIR / "auto_fetch_log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **stats
        }) + "\n")

    return stats


def main():
    if "--loop" in sys.argv:
        print(f"[auto-fetch] Starting continuous sync (interval: {SYNC_INTERVAL_MINUTES}min)")
        while True:
            stats = run_sync_cycle()
            print(f"[auto-fetch] Cycle complete: {stats['total_docs']} docs, {stats['total_chunks']} chunks")
            time.sleep(SYNC_INTERVAL_MINUTES * 60)
    else:
        stats = run_sync_cycle()
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
