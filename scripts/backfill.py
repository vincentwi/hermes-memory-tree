#!/usr/bin/env python3
"""One-time backfill: ingest all existing content from all sources.

Usage:
    python3 backfill.py              # Backfill all sources
    python3 backfill.py obsidian     # Backfill only Obsidian
    python3 backfill.py wiki         # Backfill only LLM Wiki
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from ingest import ingest_document
from providers import ObsidianProvider, WikiProvider, TheBrainProvider, AppleNotesProvider, ChatProvider, JournalProvider, SpotifyProvider

PROVIDER_MAP = {
    "obsidian": ObsidianProvider,
    "wiki": WikiProvider,
    "brain": TheBrainProvider,
    "apple-notes": AppleNotesProvider,
    "chat": ChatProvider,
    "journal": JournalProvider,
    "spotify": SpotifyProvider,
}


def backfill_source(source_id: str):
    """Backfill a single source (fetch all, no since filter)."""
    ProviderClass = PROVIDER_MAP.get(source_id)
    if not ProviderClass:
        print(f"Unknown source: {source_id}")
        return

    provider = ProviderClass()
    if not provider.health_check():
        print(f"[backfill] {source_id}: not available, skipping")
        return

    print(f"[backfill] {source_id}: fetching all documents...")
    docs = provider.fetch_changes(since=None)  # No filter = get everything
    print(f"[backfill] {source_id}: found {len(docs)} documents")

    conn = db.get_connection()
    total_chunks = 0
    total_jobs = 0

    for i, doc in enumerate(docs):
        result = ingest_document(conn, doc)
        total_chunks += result["chunks_created"]
        total_jobs += result["jobs_enqueued"]
        if (i + 1) % 10 == 0:
            print(f"[backfill] {source_id}: {i+1}/{len(docs)} docs, {total_chunks} chunks, {total_jobs} jobs")

    conn.close()
    print(f"[backfill] {source_id}: DONE — {len(docs)} docs, {total_chunks} chunks, {total_jobs} jobs enqueued")


def main():
    db.init_db()

    if len(sys.argv) > 1:
        for source_id in sys.argv[1:]:
            backfill_source(source_id)
    else:
        for source_id in ["obsidian", "wiki", "apple-notes", "chat"]:
            backfill_source(source_id)
            time.sleep(1)
        # TheBrain last due to rate limits
        backfill_source("brain")

    print("\n[backfill] Final stats:")
    conn = db.get_connection()
    stats = db.get_stats(conn)
    conn.close()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
