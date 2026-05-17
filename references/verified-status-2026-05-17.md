# Verified Functional Status — 2026-05-17

## Component Verification (30 checks)

| Component | Status | Notes |
|-----------|--------|-------|
| Unit tests (4 suites) | PASS | test_db, test_chunker, test_scorer, test_ingest |
| Pipeline CLI (ingest/stats) | PASS | Deduplication works (re-ingest = 0 new chunks) |
| Retrieval: search | PASS | Returns scored results with source paths |
| Retrieval: topic | PASS | Vincent W: 127 mentions, 85 source files |
| Retrieval: report | PASS | Entity report with wikilinks and source traceability |
| Retrieval: digest | PASS | Returns "no digest" correctly when none generated |
| Retrieval: status | PASS | Full JSON with all counters |
| Auto-fetch | PASS | 5 sources, obsidian+wiki+chat work, brain+notes conditional |
| Subconscious tick | PASS | 4 tasks evaluated, correct skip/act/escalate decisions |
| Maintenance (dedup) | PASS | 312 total duplicates merged across runs |
| Maintenance (hotness) | PASS | 10,522 entities scored |
| Sync: push-obsidian | PASS | 200 entity pages written |
| Sync: push-wiki | PASS | 96 entity pages written |
| Sync: push-graph | PASS | 200 entities + 500 relations JSON |
| Sync: push-brain | PASS | 100 thoughts created (verified via search API) |
| Database integrity | PASS | PRAGMA integrity_check = ok |
| Backfill (all sources) | PASS | journal=127, spotify=129, obsidian=828, wiki=196 |
| Fast extraction | PASS | 10-12 threads, 1.1 chunks/sec with Anthropic |
| Memory Graph MCP | PASS | 33 entities + 42 relations pushed live |
| agentmemory bridge | WARN | Daemon not running (expected if not started) |

## Final Numbers

- 10,522 entities | 9,938 relations | 1,479 chunks | 7 sources
- 196 Obsidian Memory Tree pages
- 129 Wiki entity pages
- 100 TheBrain thoughts
- 8.3 MB database
- 4 cron jobs (all midnight daily)

## Bugs Fixed This Session

1. **Subconscious NameError:** prompt variable referenced before Anthropic call block → moved prompt construction before provider selection
2. **TheBrain health check 404:** was using `/brains/{id}` → changed to `/brains` (list endpoint)
3. **TheBrain fetch 404:** was using `/brains/{id}/thoughts` → changed to `/thoughts/{brainId}`
4. **TheBrain sync NameError:** `THEBRAIN_HOME_THOUGHT` not imported in sync.py → added to import
5. **Chat provider wrong column:** `created_at` → `started_at` (REAL epoch in state.db)
6. **Spotify upload_metadata.json crash:** `str.get()` AttributeError → glob `Streaming_History_Audio_*.json` only
7. **Entity dedup not running:** hotness was all 0.0 → added recompute_hotness() called after extraction
8. **Buffer append as separate job:** caused stale dedupe key errors → inlined into extraction handler
