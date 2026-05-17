-- Memory Tree Pipeline Schema
-- Based on OpenHuman's memory-tree-pipeline architecture

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS mem_tree_chunks (
    chunk_id TEXT PRIMARY KEY,          -- SHA-256 of normalized content
    source_id TEXT NOT NULL,            -- e.g. 'obsidian', 'wiki', 'brain', 'chat'
    source_path TEXT,                   -- original file path or identifier
    content TEXT NOT NULL,              -- raw markdown content
    token_count INTEGER NOT NULL,
    lifecycle_status TEXT NOT NULL DEFAULT 'pending_extraction',
        -- pending_extraction | admitted | buffered | sealed | dropped
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_chunks_status ON mem_tree_chunks(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON mem_tree_chunks(source_id);

CREATE TABLE IF NOT EXISTS mem_tree_scores (
    chunk_id TEXT PRIMARY KEY REFERENCES mem_tree_chunks(chunk_id),
    fast_score REAL NOT NULL DEFAULT 0.0,    -- heuristic score (0-1)
    llm_score REAL,                          -- LLM-based deep score (0-1)
    entity_count INTEGER DEFAULT 0,
    info_density REAL DEFAULT 0.0,           -- unique_terms / total_terms
    recency_score REAL DEFAULT 0.0,
    scored_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS mem_tree_entity_index (
    entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,               -- person | org | project | concept | place | event
    mention_count INTEGER DEFAULT 1,
    first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    hotness REAL DEFAULT 0.0,                -- computed: mention_freq * recency * cross_source
    UNIQUE(name, entity_type)
);

CREATE INDEX IF NOT EXISTS idx_entity_hotness ON mem_tree_entity_index(hotness DESC);

CREATE TABLE IF NOT EXISTS mem_tree_entity_chunks (
    entity_id INTEGER REFERENCES mem_tree_entity_index(entity_id),
    chunk_id TEXT REFERENCES mem_tree_chunks(chunk_id),
    PRIMARY KEY(entity_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS mem_tree_relations (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    chunk_id TEXT REFERENCES mem_tree_chunks(chunk_id),
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(subject, predicate, object)
);

CREATE TABLE IF NOT EXISTS mem_tree_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                      -- extract_chunk | append_buffer | seal | topic_route | digest_daily | flush_stale
    payload_json TEXT NOT NULL DEFAULT '{}',
    dedupe_key TEXT,                         -- prevents duplicate jobs
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | failed | dead
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    available_at_ms INTEGER NOT NULL DEFAULT 0,
    locked_until_ms INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON mem_tree_jobs(status, available_at_ms);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_dedupe ON mem_tree_jobs(dedupe_key) WHERE dedupe_key IS NOT NULL AND status IN ('pending', 'running');

CREATE TABLE IF NOT EXISTS mem_tree_trees (
    node_id TEXT PRIMARY KEY,               -- e.g. 'source:wiki:L1:2025-05-17'
    tree_type TEXT NOT NULL,                 -- source | topic | global
    tree_key TEXT NOT NULL,                  -- source_id or entity_name or 'global'
    level INTEGER NOT NULL DEFAULT 0,        -- L0, L1, L2, ...
    parent_node_id TEXT REFERENCES mem_tree_trees(node_id),
    child_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_trees_type_key ON mem_tree_trees(tree_type, tree_key);

CREATE TABLE IF NOT EXISTS mem_tree_buffers (
    buffer_id TEXT PRIMARY KEY,             -- e.g. 'source:wiki:L0:current'
    tree_type TEXT NOT NULL,
    tree_key TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    chunk_ids_json TEXT NOT NULL DEFAULT '[]',  -- JSON array of chunk_ids
    chunk_count INTEGER DEFAULT 0,
    max_chunks INTEGER DEFAULT 10,           -- seal threshold
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS mem_tree_summaries (
    summary_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES mem_tree_trees(node_id),
    content TEXT NOT NULL,                   -- markdown summary
    source_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    entity_ids_json TEXT NOT NULL DEFAULT '[]',
    token_count INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS mem_tree_sync_state (
    source_id TEXT PRIMARY KEY,
    last_sync_ts TEXT,
    cursor TEXT,
    dedup_set_hash TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    last_error TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS mem_tree_subconscious_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    task_type TEXT NOT NULL,                  -- system | user
    decision TEXT NOT NULL,                   -- skip | act | escalate
    reasoning TEXT,
    action_taken TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
