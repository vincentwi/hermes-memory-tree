# Parallel LLM Extraction Pattern

Reusable pattern for bulk processing items through an LLM API (entity extraction, summarization, classification) when you have hundreds or thousands of items and a single-threaded approach is too slow.

## The Problem

Default worker pool: ~6 items/min (sequential job queue with SQLite claim/release).
For 1,000 items, that's ~2.7 hours. Unacceptable for interactive use.

## Solution: ThreadPoolExecutor + Atomic Status Guards

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

lock = threading.Lock()
stats = {"processed": 0, "errors": 0}

def process_item(item_id, content):
    """Process one item through the LLM."""
    try:
        result = call_llm(content)  # Anthropic, Groq, etc.
        with lock:
            # Atomic check: skip if another thread already processed this
            row = conn.execute("SELECT status FROM items WHERE id = ?", (item_id,)).fetchone()
            if row["status"] != "pending":
                return  # Already done by queue worker
            # Write results
            conn.execute("UPDATE items SET status = 'done', ... WHERE id = ?", (item_id,))
            conn.commit()
            stats["processed"] += 1
    except Exception as e:
        with lock:
            stats["errors"] += 1

# Grab batch, process in parallel
items = conn.execute("SELECT * FROM items WHERE status = 'pending' ORDER BY RANDOM() LIMIT 300").fetchall()
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(process_item, r["id"], r["content"]): r["id"] for r in items}
    for f in as_completed(futures):
        pass
```

## Key Design Points

1. **ORDER BY RANDOM()** — if running alongside queue workers, randomizing avoids both systems starting from the same end and colliding on every item.

2. **Atomic status guard inside the lock** — re-check status before writing. Another thread or the queue worker may have claimed the item between SELECT and UPDATE.

3. **Threading lock for SQLite** — SQLite handles concurrent reads but concurrent writes from multiple threads in the same process need serialization. The `with lock:` block around all writes prevents "database is locked" errors.

4. **Safe to run alongside queue workers** — the queue workers use `claim_job()` with SQLite's atomic UPDATE...RETURNING. The fast extractor uses a different path (direct status check). They don't interfere because both check status before writing.

5. **10 threads for Anthropic** — Anthropic's API handles 10+ concurrent requests well. Groq free tier is more limited. Adjust `max_workers` to match your provider's concurrency tolerance.

## Results (Memory Tree Pipeline, 2026-05-17)

- Single worker pool: ~6 chunks/min → 558 chunks would take ~93 min
- 3 worker pools + fast_extract(10 threads): 558 → 0 in ~3 minutes
- 30x speedup for bulk extraction

## When to Use

- Initial backfill of a knowledge base (hundreds of documents)
- Catch-up after downtime (accumulated pending items)
- Any batch where you have 100+ items needing LLM processing
- NOT for steady-state (the cron + worker pool handles incremental flow fine)
