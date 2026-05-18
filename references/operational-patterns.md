# Memory Tree Pipeline — Operational Patterns

Learned from the initial deployment session (2026-05-17).

## Parallel Extraction (10-12x speedup)

The job queue workers process ~6 chunks/minute (single pool, 3 workers).
For bulk processing, bypass the queue with `fast_extract.py`:

```bash
# 10 threads, process up to 300 chunks
python3 fast_extract.py 10 300
```

This uses ThreadPoolExecutor + a lock for DB writes. Safe to run
alongside queue workers — atomic `lifecycle_status` checks prevent
double-processing. Achieved 1.1-1.4 chunks/sec (vs 0.1 for queue).

**When to use:** Initial backfill, catching up after adding new sources,
processing large batches. NOT for steady-state (cron handles that).

## Entity Deduplication Patterns

Run `maintenance.py dedup` after any bulk extraction. Key alias maps:
- Case-insensitive: "Vincent W" / "vincent-w" / "Vincent" → merge
- City aliases: "San Francisco" / "SF" / "San Francisco, CA"
- Tech terms: "css" / "CSS", "rss" / "RSS"

The dedup function merges mention counts, moves chunk links, deletes
the duplicate row. Always keeps the variant with most mentions.

**Pitfall:** Entity type duplication still exists — an entity can appear
as both "project" and "concept" (e.g., MentraOS). The dedup only merges
within the same entity_type. Cross-type dedup is a TODO.

## Hotness Formula

```
hotness = mention_count × recency_weight × cross_source_bonus
```

- recency_weight: 1.0 if today, linear decay to 0.1 at 30+ days
- cross_source_bonus: 1.5x if entity appears in 2+ distinct source_ids

Run `maintenance.py hotness` after extraction to recompute. Workers
also call it per-chunk but batch recompute is more accurate.

## Subconscious Loop — LLM Provider

Uses Anthropic as primary (Groq returns 403 with the current key).
The prompt must be defined BEFORE the Anthropic try block — it was
a bug when the Anthropic block referenced `prompt` before assignment.

## TheBrain API Gotchas

- Full UUID required everywhere (not truncated 8-char)
- Create thoughts: `POST /thoughts/{brainId}` (NOT `/brains/{brainId}/thoughts`)
- Health check: `GET /brains` (lists all brains, returns 200)
- Search: `GET /search/{brainId}?queryText=X&maxResults=N`
- The `/brains/{brainId}` endpoint returns 404 — don't use for health

## agentmemory Deployment

agentmemory (v0.9.18) binds to 127.0.0.1 only. To expose on a
remote machine (Mac Mini via Tailscale):

1. SSH tunnel: `ssh -f -N -L 3211:localhost:3111 user@host`
2. Or Python TCP proxy on the remote (see sysadmin-extended skill)
3. socat may not be installed on macOS — Python proxy is reliable

The `preferences.json` file must exist with `skipSplash: true` to
bypass the interactive wizard when running non-interactively.

## state.db Schema

Hermes state.db uses `started_at` (REAL, Unix epoch) NOT `created_at`.
Has `title` TEXT (nullable) but NO `preview` column. Messages are in
a separate `messages` table joined by `session_id`.

The state.db was recovered from corruption during this session:
`.dump` → fix ROLLBACK→COMMIT → add OR IGNORE → reimport → rebuild FTS.

## Cron Wrapper Pattern

Cron `script` param must be a filename in `~/.hermes/scripts/` — not
an absolute path. Create thin wrappers:
```python
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/memory-tree-pipeline/scripts"))
import db; db.init_db()
from module import function
function()
```
