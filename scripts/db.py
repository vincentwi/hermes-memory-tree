"""SQLite database connection and helpers for Memory Tree Pipeline."""
import sqlite3
import json
import time
import os
from pathlib import Path
from typing import Optional
from models import (
    Chunk, Score, Entity, Relation, Job, JobKind, JobStatus,
    LifecycleStatus, TreeType, EntityType
)

DB_DIR = Path.home() / ".hermes" / "memory_tree"
DB_PATH = DB_DIR / "chunks.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize the database from schema.sql."""
    conn = get_connection()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.close()


def insert_chunk(conn: sqlite3.Connection, chunk: Chunk):
    """Insert a chunk, ignoring duplicates."""
    conn.execute(
        """INSERT OR IGNORE INTO mem_tree_chunks
           (chunk_id, source_id, source_path, content, token_count, lifecycle_status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (chunk.chunk_id, chunk.source_id, chunk.source_path,
         chunk.content, chunk.token_count, chunk.lifecycle_status.value)
    )


def insert_score(conn: sqlite3.Connection, score: Score):
    """Insert or replace a score."""
    conn.execute(
        """INSERT OR REPLACE INTO mem_tree_scores
           (chunk_id, fast_score, llm_score, entity_count, info_density, recency_score)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (score.chunk_id, score.fast_score, score.llm_score,
         score.entity_count, score.info_density, score.recency_score)
    )


def update_chunk_status(conn: sqlite3.Connection, chunk_id: str, status: LifecycleStatus):
    """Update lifecycle status of a chunk."""
    conn.execute(
        """UPDATE mem_tree_chunks SET lifecycle_status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
           WHERE chunk_id = ?""",
        (status.value, chunk_id)
    )


def enqueue_job(conn: sqlite3.Connection, job: Job) -> int:
    """Enqueue a job. Returns job_id."""
    cursor = conn.execute(
        """INSERT INTO mem_tree_jobs (kind, payload_json, dedupe_key, status, available_at_ms)
           VALUES (?, ?, ?, 'pending', ?)""",
        (job.kind.value, job.payload_json, job.dedupe_key,
         int(time.time() * 1000))
    )
    return cursor.lastrowid


def claim_job(conn: sqlite3.Connection) -> Optional[dict]:
    """Claim the next available job. Returns row dict or None."""
    now_ms = int(time.time() * 1000)
    lock_until = now_ms + 60_000  # 60s lease
    row = conn.execute(
        """UPDATE mem_tree_jobs
           SET status = 'running', locked_until_ms = ?, attempts = attempts + 1
           WHERE job_id = (
               SELECT job_id FROM mem_tree_jobs
               WHERE status = 'pending' AND available_at_ms <= ?
               ORDER BY job_id ASC LIMIT 1
           )
           RETURNING *""",
        (lock_until, now_ms)
    ).fetchone()
    return dict(row) if row else None


def complete_job(conn: sqlite3.Connection, job_id: int):
    """Mark a job as done."""
    conn.execute(
        """UPDATE mem_tree_jobs
           SET status = 'done', completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
           WHERE job_id = ?""",
        (job_id,)
    )


def fail_job(conn: sqlite3.Connection, job_id: int, error: str):
    """Mark a job as failed. If max attempts reached, mark as dead."""
    conn.execute(
        """UPDATE mem_tree_jobs
           SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'failed' END,
               last_error = ?,
               locked_until_ms = 0
           WHERE job_id = ?""",
        (error, job_id)
    )
    # Reset failed (not dead) jobs to pending for retry
    conn.execute(
        """UPDATE mem_tree_jobs SET status = 'pending'
           WHERE job_id = ? AND status = 'failed'""",
        (job_id,)
    )


def recover_stale_jobs(conn: sqlite3.Connection):
    """Reset jobs that have been running past their lock lease."""
    now_ms = int(time.time() * 1000)
    conn.execute(
        """UPDATE mem_tree_jobs SET status = 'pending', locked_until_ms = 0
           WHERE status = 'running' AND locked_until_ms < ?""",
        (now_ms,)
    )
    conn.commit()


def upsert_entity(conn: sqlite3.Connection, entity: Entity) -> int:
    """Insert or update an entity. Returns entity_id."""
    conn.execute(
        """INSERT INTO mem_tree_entity_index (name, entity_type, mention_count, hotness)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(name, entity_type) DO UPDATE SET
               mention_count = mention_count + excluded.mention_count,
               last_seen = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')""",
        (entity.name, entity.entity_type.value, entity.mention_count, entity.hotness)
    )
    row = conn.execute(
        "SELECT entity_id FROM mem_tree_entity_index WHERE name = ? AND entity_type = ?",
        (entity.name, entity.entity_type.value)
    ).fetchone()
    return row["entity_id"]


def link_entity_chunk(conn: sqlite3.Connection, entity_id: int, chunk_id: str):
    """Link an entity to a chunk."""
    conn.execute(
        "INSERT OR IGNORE INTO mem_tree_entity_chunks (entity_id, chunk_id) VALUES (?, ?)",
        (entity_id, chunk_id)
    )


def upsert_relation(conn: sqlite3.Connection, rel: Relation):
    """Insert or ignore a relation."""
    conn.execute(
        """INSERT OR IGNORE INTO mem_tree_relations (subject, predicate, object, chunk_id, confidence)
           VALUES (?, ?, ?, ?, ?)""",
        (rel.subject, rel.predicate, rel.object, rel.chunk_id, rel.confidence)
    )


def get_buffer(conn: sqlite3.Connection, tree_type: str, tree_key: str, level: int = 0) -> Optional[dict]:
    """Get or create a buffer for a tree node."""
    buffer_id = f"{tree_type}:{tree_key}:L{level}:current"
    row = conn.execute(
        "SELECT * FROM mem_tree_buffers WHERE buffer_id = ?", (buffer_id,)
    ).fetchone()
    if row:
        return dict(row)
    # Create new buffer
    conn.execute(
        """INSERT INTO mem_tree_buffers (buffer_id, tree_type, tree_key, level)
           VALUES (?, ?, ?, ?)""",
        (buffer_id, tree_type, tree_key, level)
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM mem_tree_buffers WHERE buffer_id = ?", (buffer_id,)
    ).fetchone())


def append_to_buffer(conn: sqlite3.Connection, buffer_id: str, chunk_id: str) -> int:
    """Add a chunk to a buffer. Returns new chunk_count."""
    row = conn.execute(
        "SELECT chunk_ids_json, chunk_count FROM mem_tree_buffers WHERE buffer_id = ?",
        (buffer_id,)
    ).fetchone()
    chunk_ids = json.loads(row["chunk_ids_json"])
    chunk_ids.append(chunk_id)
    new_count = len(chunk_ids)
    conn.execute(
        """UPDATE mem_tree_buffers
           SET chunk_ids_json = ?, chunk_count = ?,
               updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
           WHERE buffer_id = ?""",
        (json.dumps(chunk_ids), new_count, buffer_id)
    )
    return new_count


def entity_dedup(conn: sqlite3.Connection) -> int:
    """Merge duplicate entities (case-insensitive + known aliases). Returns merge count."""
    ALIASES = {
        'vincent w': ['vincent-w', 'vincent', 'vincent w.'],
        'san francisco': ['sf', 'san francisco, ca', 'san francisco bay area'],
        'new york': ['nyc', 'new york city', 'new york, ny'],
        'css': ['CSS'],
        'html': ['HTML'],
        'javascript': ['js', 'JS', 'Javascript'],
    }

    merged = 0

    # 1) Case-insensitive dedup: group by LOWER(name)+entity_type
    rows = conn.execute(
        '''SELECT LOWER(name) as lname, entity_type, COUNT(*) as cnt
           FROM mem_tree_entity_index
           GROUP BY LOWER(name), entity_type
           HAVING cnt > 1'''
    ).fetchall()

    for row in rows:
        variants = conn.execute(
            '''SELECT entity_id, name, mention_count
               FROM mem_tree_entity_index
               WHERE LOWER(name) = ? AND entity_type = ?
               ORDER BY mention_count DESC''',
            (row['lname'], row['entity_type'])
        ).fetchall()
        if len(variants) < 2:
            continue
        keeper = variants[0]
        for dup in variants[1:]:
            conn.execute('UPDATE OR IGNORE mem_tree_entity_chunks SET entity_id = ? WHERE entity_id = ?',
                         (keeper['entity_id'], dup['entity_id']))
            conn.execute('DELETE FROM mem_tree_entity_chunks WHERE entity_id = ?', (dup['entity_id'],))
            conn.execute('UPDATE mem_tree_entity_index SET mention_count = mention_count + ? WHERE entity_id = ?',
                         (dup['mention_count'], keeper['entity_id']))
            conn.execute('DELETE FROM mem_tree_entity_index WHERE entity_id = ?', (dup['entity_id'],))
            merged += 1

    # 2) Known alias merges
    for canonical, aliases in ALIASES.items():
        keeper_row = conn.execute(
            'SELECT entity_id, mention_count FROM mem_tree_entity_index WHERE LOWER(name) = ?',
            (canonical,)
        ).fetchone()
        if not keeper_row:
            continue
        for alias in aliases:
            dup_row = conn.execute(
                'SELECT entity_id, mention_count FROM mem_tree_entity_index WHERE LOWER(name) = ?',
                (alias.lower(),)
            ).fetchone()
            if dup_row and dup_row['entity_id'] != keeper_row['entity_id']:
                conn.execute('UPDATE OR IGNORE mem_tree_entity_chunks SET entity_id = ? WHERE entity_id = ?',
                             (keeper_row['entity_id'], dup_row['entity_id']))
                conn.execute('DELETE FROM mem_tree_entity_chunks WHERE entity_id = ?', (dup_row['entity_id'],))
                conn.execute('UPDATE mem_tree_entity_index SET mention_count = mention_count + ? WHERE entity_id = ?',
                             (dup_row['mention_count'], keeper_row['entity_id']))
                conn.execute('DELETE FROM mem_tree_entity_index WHERE entity_id = ?', (dup_row['entity_id'],))
                merged += 1

    conn.commit()
    return merged


def recompute_hotness(conn: sqlite3.Connection) -> int:
    """Recompute hotness for all entities. Returns count updated."""
    from datetime import datetime, timezone as tz
    now = datetime.now(tz.utc)

    entities = conn.execute('SELECT entity_id, mention_count, last_seen FROM mem_tree_entity_index').fetchall()
    updated = 0
    for e in entities:
        # Recency weight: 1.0 today, 0.5 at 7 days, 0.1 at 30+ days
        try:
            last = datetime.fromisoformat(e['last_seen'].replace('Z', '+00:00'))
            days = (now - last).days
            recency = max(0.1, 1.0 - (days / 30.0))
        except (ValueError, TypeError, AttributeError):
            recency = 0.5

        # Cross-source bonus: 1.5x if entity appears in 2+ source_ids
        src = conn.execute(
            '''SELECT COUNT(DISTINCT c.source_id) as src_count
               FROM mem_tree_entity_chunks ec
               JOIN mem_tree_chunks c ON ec.chunk_id = c.chunk_id
               WHERE ec.entity_id = ?''',
            (e['entity_id'],)
        ).fetchone()
        cross_source = 1.5 if (src and src['src_count'] >= 2) else 1.0

        hotness = e['mention_count'] * recency * cross_source
        conn.execute('UPDATE mem_tree_entity_index SET hotness = ? WHERE entity_id = ?',
                     (round(hotness, 2), e['entity_id']))
        updated += 1

    conn.commit()
    return updated


def get_stats(conn: sqlite3.Connection) -> dict:
    """Get pipeline statistics."""
    stats = {}
    for status in LifecycleStatus:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM mem_tree_chunks WHERE lifecycle_status = ?",
            (status.value,)
        ).fetchone()
        stats[f"chunks_{status.value}"] = row["cnt"]
    row = conn.execute("SELECT COUNT(*) as cnt FROM mem_tree_entity_index").fetchone()
    stats["entities"] = row["cnt"]
    row = conn.execute("SELECT COUNT(*) as cnt FROM mem_tree_relations").fetchone()
    stats["relations"] = row["cnt"]
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM mem_tree_jobs WHERE status = 'pending'"
    ).fetchone()
    stats["pending_jobs"] = row["cnt"]
    return stats
