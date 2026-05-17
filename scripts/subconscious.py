#!/usr/bin/env python3
"""Subconscious loop — background task evaluation and execution.

Periodically reads Memory Tree state, evaluates tasks, and acts or escalates.

Usage:
    python3 subconscious.py tick     # Run one evaluation tick
    python3 subconscious.py tasks    # List registered tasks
    python3 subconscious.py add <description>  # Add a user task
"""
import sys
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from config import (
    GROQ_API_KEY, GROQ_MODEL, GROQ_API_URL,
    MEMORY_TREE_DIR, SUBCONSCIOUS_CONTEXT_BUDGET
)

TASKS_FILE = MEMORY_TREE_DIR / "subconscious_tasks.json"
LOG_FILE = MEMORY_TREE_DIR / "subconscious_log.jsonl"


def load_tasks() -> list:
    """Load task registry."""
    if TASKS_FILE.exists():
        return json.loads(TASKS_FILE.read_text())

    # Seed system tasks
    default_tasks = [
        {"id": "sys-stale-sources", "type": "system", "enabled": True,
         "description": "Check for stale sync sources (no updates in >24h)"},
        {"id": "sys-memory-growth", "type": "system", "enabled": True,
         "description": "Review memory tree growth and flag unusual patterns"},
        {"id": "sys-extraction-quality", "type": "system", "enabled": True,
         "description": "Monitor chunk extraction quality (drop rate, entity yield)"},
        {"id": "sys-graph-integrity", "type": "system", "enabled": True,
         "description": "Weekly knowledge graph integrity check (orphan entities, stale relations)"},
    ]
    save_tasks(default_tasks)
    return default_tasks


def save_tasks(tasks: list):
    """Save task registry."""
    MEMORY_TREE_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))


def build_situation_report(conn) -> str:
    """Build a situation report from Memory Tree state."""
    stats = db.get_stats(conn)

    # Recent summaries
    recent = conn.execute(
        """SELECT content FROM mem_tree_summaries
           ORDER BY created_at DESC LIMIT 3"""
    ).fetchall()

    # Hot entities
    hot = conn.execute(
        """SELECT name, entity_type, hotness, mention_count
           FROM mem_tree_entity_index
           ORDER BY hotness DESC LIMIT 10"""
    ).fetchall()

    # Sync state
    sync = conn.execute(
        "SELECT * FROM mem_tree_sync_state"
    ).fetchall()

    report = f"""# Situation Report ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})

## Pipeline Stats
- Chunks: {stats.get('chunks_pending_extraction', 0)} pending, {stats.get('chunks_admitted', 0)} admitted, {stats.get('chunks_sealed', 0)} sealed, {stats.get('chunks_dropped', 0)} dropped
- Entities: {stats.get('entities', 0)}
- Relations: {stats.get('relations', 0)}
- Pending jobs: {stats.get('pending_jobs', 0)}

## Hot Entities
"""
    for e in hot:
        report += f"- {e['name']} ({e['entity_type']}) — hotness: {e['hotness']:.1f}, mentions: {e['mention_count']}\n"

    report += "\n## Recent Summaries\n"
    for s in recent:
        report += f"\n{s['content'][:300]}...\n"

    report += "\n## Sync State\n"
    for s in sync:
        report += f"- {s['source_id']}: last sync {s['last_sync_ts'] or 'never'}, failures: {s['consecutive_failures']}\n"

    return report[:SUBCONSCIOUS_CONTEXT_BUDGET * 4]  # Rough token limit


def evaluate_task(task: dict, situation: str) -> dict:
    """Evaluate a task against the situation report. Uses Anthropic (primary) or Groq (fallback)."""
    prompt = f"""You are a background monitoring agent. Given the current system state and a task description, decide what to do.

TASK: {task['description']}

SITUATION:
{situation}

Respond with JSON:
{{"decision": "skip|act|escalate", "reasoning": "brief explanation", "action": "what to do if acting"}}

- skip: nothing to do right now
- act: you can handle this directly (describe action)
- escalate: needs human attention (describe what and why)"""

    # Try Anthropic first (more reliable)
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        from config import ANTHROPIC_MODEL, ANTHROPIC_API_URL
        try:
            payload = json.dumps({
                "model": ANTHROPIC_MODEL,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8")
            req = Request(ANTHROPIC_API_URL, data=payload, headers={
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }, method="POST")
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                text = result["content"][0]["text"].strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("```", 1)[0]
                return json.loads(text.strip())
        except Exception:
            pass

    # Groq fallback
    api_key = GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return {"decision": "skip", "reasoning": "No LLM API key available"}

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise system monitor. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 300,
        "response_format": {"type": "json_object"}
    }).encode("utf-8")

    try:
        req = Request(GROQ_API_URL, data=payload, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, method="POST")
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            text = result["choices"][0]["message"]["content"]
            return json.loads(text)
    except Exception as e:
        return {"decision": "skip", "reasoning": f"Evaluation error: {str(e)[:100]}"}


def run_tick():
    """Run one evaluation tick."""
    db.init_db()
    conn = db.get_connection()
    tasks = load_tasks()
    active_tasks = [t for t in tasks if t.get("enabled", True)]

    if not active_tasks:
        print("[subconscious] No active tasks")
        return

    situation = build_situation_report(conn)
    results = []

    for task in active_tasks:
        evaluation = evaluate_task(task, situation)
        decision = evaluation.get("decision", "skip")

        # Log
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task["id"],
            "task_type": task["type"],
            "decision": decision,
            "reasoning": evaluation.get("reasoning", ""),
            "action": evaluation.get("action", "")
        }

        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        results.append(log_entry)

        if decision == "escalate":
            print(f"[subconscious] ESCALATE: {task['description']}")
            print(f"  Reason: {evaluation.get('reasoning', '')}")
            print(f"  Action: {evaluation.get('action', '')}")

    conn.close()
    print(f"[subconscious] Tick complete: {len(results)} tasks evaluated")
    for r in results:
        print(f"  {r['task_id']}: {r['decision']} — {r['reasoning'][:80]}")


def add_task(description: str):
    """Add a user task."""
    tasks = load_tasks()
    task_id = f"user-{int(time.time())}"
    tasks.append({
        "id": task_id,
        "type": "user",
        "enabled": True,
        "description": description
    })
    save_tasks(tasks)
    print(f"[subconscious] Added task {task_id}: {description}")


def list_tasks():
    """List all tasks."""
    tasks = load_tasks()
    for t in tasks:
        status = "ON" if t.get("enabled", True) else "OFF"
        print(f"  [{status}] {t['id']}: {t['description']}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "tick":
        run_tick()
    elif cmd == "tasks":
        list_tasks()
    elif cmd == "add" and len(sys.argv) >= 3:
        add_task(" ".join(sys.argv[2:]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
