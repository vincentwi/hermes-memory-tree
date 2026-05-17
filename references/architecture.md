# Memory Tree Pipeline — Architecture

## Inspired By
[OpenHuman](https://github.com/tinyhumansai/openhuman) by tinyhumansai — adapted from Rust/Tauri to Python for Hermes Agent.

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    SOURCE PROVIDERS                          │
│  Obsidian │ LLM Wiki │ TheBrain │ Apple Notes │ Chat        │
└─────┬───────────┬──────────┬──────────┬──────────┬──────────┘
      │           │          │          │          │
      ▼           ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────┐
│                    AUTO-FETCH (20min cron)                    │
│  Per-source sync state │ Change detection │ Rate limiting     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    INGEST (Hot Path)                          │
│  Canonicalize → Chunk (≤3k tokens) → Fast Score → Persist    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    JOB QUEUE (SQLite)                         │
│  extract_chunk │ append_buffer │ seal │ topic_route │ etc    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    WORKERS (3 parallel)                       │
│  LLM extraction → Entity/Relation storage → Buffer append    │
│  Semaphore(2) for LLM calls │ Stale lock recovery            │
└──────────┬──────────┬──────────┬────────────────────────────┘
           │          │          │
           ▼          ▼          ▼
┌──────────────┐┌──────────────┐┌──────────────┐
│ Source Trees  ││ Topic Trees  ││ Global Tree  │
│ L0→L1→L2     ││ Per-entity   ││ Daily digest │
│ Per-source    ││ Hotness-gate ││ → weekly     │
└──────┬───────┘└──────┬───────┘└──────┬───────┘
       │               │               │
       ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                    SYNC ENGINE                                │
│  → Obsidian (entity pages) │ → LLM Wiki (entity pages)      │
│  → TheBrain (thoughts)     │ → Memory Graph (MCP)            │
│  → agentmemory (REST)                                        │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    SUBCONSCIOUS (5min cron)                   │
│  Situation report → Task evaluation (Groq) → Act/Escalate    │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **Python, not Rust** — OpenHuman uses Rust/Tauri; we use Python for compatibility with Hermes Agent's skill system and cron jobs.
2. **SQLite, not Neo4j** — Memory Graph MCP + TheBrain cover the graph layer; SQLite handles the job queue and chunk storage.
3. **Groq for LLM** — Free tier, fast inference, good for entity extraction and summarization.
4. **Obsidian as UI** — No custom frontend; Obsidian IS the knowledge browser.
5. **Cron, not daemon** — Hermes cron jobs instead of long-running processes; workers run as needed.
