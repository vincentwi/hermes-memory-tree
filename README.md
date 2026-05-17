# Memory Tree Pipeline — OpenHuman-Inspired Memory System for Hermes Agent

A drop-in skill that transforms Hermes Agent's flat-text memory into a hierarchical, auto-syncing knowledge system — inspired by [OpenHuman](https://github.com/tinyhumansai/openhuman) by tinyhumansai.

## What It Does

Turns disconnected knowledge stores into one unified memory pipeline:

- **Before:** 2.2KB flat MEMORY.md, manual wiki/Obsidian maintenance, empty knowledge graph
- **After:** 9,000+ entities, 8,700+ relations, auto-syncing across 7 sources, hierarchical summaries

## Architecture

Adapted from OpenHuman's [Memory Tree Pipeline](https://tinyhumans.gitbook.io/openhuman/features/obsidian-wiki/memory-tree) and [architecture](https://github.com/tinyhumansai/openhuman/blob/main/gitbooks/developing/architecture.md):

```
Sources (7)           Pipeline (6 stages)              Outputs (5 targets)
┌──────────┐    ┌──────────────────────────┐    ┌────────────────────┐
│ Obsidian │───>│ Ingest → Chunk → Score   │───>│ Obsidian (pages)   │
│ LLM Wiki │───>│ → Extract → Buffer       │───>│ LLM Wiki (entities)│
│ TheBrain │───>│ → Seal (summaries)        │───>│ TheBrain (thoughts)│
│ Apple Notes──>│                            │───>│ Memory Graph (MCP) │
│ Chat     │───>│ SQLite job queue           │───>│ agentmemory (REST) │
│ Journal  │───>│ 3-12 parallel workers      │    └────────────────────┘
│ Spotify  │───>│ Anthropic/Groq LLM        │
└──────────┘    └──────────────────────────┘
                           │
                ┌──────────▼──────────┐
                │ Subconscious Loop   │
                │ (evaluate → act)    │
                └─────────────────────┘
```

## Features (from OpenHuman)

| Feature | OpenHuman Reference | Our Implementation |
|---------|--------------------|--------------------|
| **Memory Tree** | [memory-tree](https://tinyhumans.gitbook.io/openhuman/features/obsidian-wiki/memory-tree) | 6-stage async pipeline with source/topic/global trees |
| **Auto-Fetch** | [auto-fetch](https://tinyhumans.gitbook.io/openhuman/features/obsidian-wiki/auto-fetch) | 7 source providers with per-source sync state |
| **Obsidian Wiki** | [memory-tree-pipeline](https://github.com/tinyhumansai/openhuman/blob/main/gitbooks/developing/memory-tree-pipeline.excalidraw) | Bidirectional sync, auto-generated entity pages |
| **agentmemory** | [agentmemory-backend](https://tinyhumans.gitbook.io/openhuman/features/obsidian-wiki/agentmemory-backend) | REST bridge for Claude Code/Cursor/Codex sharing |
| **Subconscious** | [subconscious](https://tinyhumans.gitbook.io/openhuman/features/subconscious) | Background task evaluation with skip/act/escalate |
| **Memory Sync** | [memory-sync-functions](https://github.com/tinyhumansai/openhuman/blob/main/docs/memory-sync-functions.md) | Unified sync engine pushing to 5 targets |

### Key Differences from OpenHuman

| Aspect | OpenHuman | This Skill |
|--------|-----------|------------|
| Runtime | Rust + Tauri + React | Python (Hermes skill system) |
| Graph DB | Neo4j | Hermes Memory Graph MCP + TheBrain API |
| UI | Custom desktop app | Obsidian vault + terminal CLI |
| Scheduling | Internal cron (5s tick) | Hermes cron jobs |
| LLM | Configurable (local/cloud) | Anthropic primary, Groq fallback |
| Encryption | AES-256-GCM | macOS FileVault (local-only) |

## Quick Start

```bash
# 1. Initialize database
cd ~/.hermes/skills/memory-tree-pipeline/scripts
python3 pipeline.py stats

# 2. Backfill existing content
python3 backfill.py obsidian wiki

# 3. Extract entities (parallel)
python3 fast_extract.py 10 500

# 4. Run maintenance (dedup + hotness)
python3 maintenance.py all

# 5. Push to all targets
python3 sync.py push-all

# 6. Browse entities
python3 retrieve.py report --limit=20
python3 retrieve.py search "your query"
python3 retrieve.py topic "Entity Name"
```

## Components

| Script | Purpose |
|--------|---------|
| `pipeline.py` | Main CLI: ingest, workers, stats, digest, flush |
| `fast_extract.py` | Parallel threaded extraction (10-12x faster) |
| `auto_fetch.py` | Periodic sync from all 7 sources |
| `backfill.py` | One-time bulk ingest of existing content |
| `retrieve.py` | Search, drill-down, topic browse, entity report |
| `sync.py` | Push entities to Obsidian, Wiki, TheBrain, Memory Graph |
| `agentmemory_bridge.py` | Cross-agent memory via agentmemory daemon |
| `subconscious.py` | Background task evaluation and escalation |
| `maintenance.py` | Entity dedup, hotness recompute, buffer fixes |

## Source Providers

| Provider | Source | Detection Method |
|----------|--------|-----------------|
| Obsidian | `~/Documents/Obsidian Vault/` | File mtime comparison |
| LLM Wiki | `~/llm-wiki/` | Git diff / mtime fallback |
| TheBrain | api.bra.in REST API | API poll |
| Apple Notes | `memo` CLI | Search by date |
| Chat | `~/.hermes/state.db` | Session timestamp |
| Journal | `~/Documents/AppleJournalEntries/` | HTML file mtime |
| Spotify | Extended streaming history JSON | File parsing |

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | LLM extraction and summarization |
| `GROQ_API_KEY` | No | Fallback LLM (free tier) |
| `THEBRAIN_API_KEY` | No | TheBrain sync |
| `OPENAI_API_KEY` | No | Embeddings (text-embedding-3-small) |

Keys are auto-loaded from `~/.hermes/.env`.

## Cron Jobs

All run at midnight daily:
- `memory_tree_auto_fetch.py` — Pull changes from all sources
- `memory_tree_subconscious.py` — Evaluate tasks against memory state
- `memory_tree_digest.py` — Build global daily summary
- `memory_tree_sync.py` — Push entities to all targets

## Credits

Architecture and concepts adapted from [OpenHuman](https://github.com/tinyhumansai/openhuman) by [tinyhumansai](https://github.com/tinyhumansai). Key references:

- [Memory Tree Pipeline](https://tinyhumans.gitbook.io/openhuman/features/obsidian-wiki/memory-tree) — hierarchical chunk→buffer→seal pipeline
- [Auto-Fetch](https://tinyhumans.gitbook.io/openhuman/features/obsidian-wiki/auto-fetch) — periodic integration sync pattern
- [agentmemory Backend](https://tinyhumans.gitbook.io/openhuman/features/obsidian-wiki/agentmemory-backend) — cross-agent memory sharing
- [Subconscious Loop](https://tinyhumans.gitbook.io/openhuman/features/subconscious) — background task evaluation
- [Architecture](https://github.com/tinyhumansai/openhuman/blob/main/gitbooks/developing/architecture.md) — system design
- [Memory Sync Functions](https://github.com/tinyhumansai/openhuman/blob/main/docs/memory-sync-functions.md) — consumer API patterns
- [Pipeline Diagram](https://github.com/tinyhumansai/openhuman/blob/main/gitbooks/developing/memory-tree-pipeline.excalidraw) — 6-stage pipeline flow

## License

MIT — same as Hermes Agent
