"""Configuration for Memory Tree Pipeline."""
import os
import json
from pathlib import Path

# Load .env file if it exists (Hermes stores API keys there)
_env_path = Path.home() / ".hermes" / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            # Don't override existing env vars
            if key and not os.getenv(key):
                os.environ[key] = val

# Directories
HERMES_DIR = Path.home() / ".hermes"
MEMORY_TREE_DIR = HERMES_DIR / "memory_tree"
SKILL_DIR = HERMES_DIR / "skills" / "memory-tree-pipeline"

# Data sources
OBSIDIAN_VAULT = Path.home() / "Documents" / "Obsidian Vault"
LLM_WIKI = Path.home() / "llm-wiki"

# TheBrain
THEBRAIN_API = "https://api.bra.in"
THEBRAIN_BRAIN_ID = os.getenv("THEBRAIN_BRAIN_ID", "")
THEBRAIN_HOME_THOUGHT = os.getenv("THEBRAIN_HOME_THOUGHT", "")
THEBRAIN_API_KEY = os.getenv("THEBRAIN_API_KEY", "")

# LLM APIs — prefer Anthropic (already configured as Hermes provider)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# Use Anthropic if key available, otherwise fall back to Groq
USE_ANTHROPIC = bool(ANTHROPIC_API_KEY)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL = "text-embedding-3-small"

# agentmemory
AGENTMEMORY_URL = os.getenv("AGENTMEMORY_URL", "http://100.116.27.60:3111")

# Pipeline settings
MAX_CHUNK_TOKENS = 3000
BUFFER_SEAL_THRESHOLD = 10  # chunks before sealing L0 → L1
WORKER_COUNT = 5
LLM_CONCURRENCY = 3
FAST_SCORE_DROP_THRESHOLD = 0.15  # chunks below this are dropped

# Auto-fetch
SYNC_INTERVAL_MINUTES = 20
FSWATCH_DEBOUNCE_SECONDS = 30

# Subconscious
SUBCONSCIOUS_TICK_MINUTES = 5
SUBCONSCIOUS_EVAL_MODEL = "groq/llama-3.3-70b-versatile"
SUBCONSCIOUS_EXEC_MODEL = "anthropic/claude-sonnet-4"
SUBCONSCIOUS_CONTEXT_BUDGET = 4000  # tokens

# Sync state file
SYNC_STATE_PATH = MEMORY_TREE_DIR / "sync_state.json"


def load_sync_state() -> dict:
    """Load sync state from disk."""
    if SYNC_STATE_PATH.exists():
        return json.loads(SYNC_STATE_PATH.read_text())
    return {}


def save_sync_state(state: dict):
    """Save sync state to disk."""
    MEMORY_TREE_DIR.mkdir(parents=True, exist_ok=True)
    SYNC_STATE_PATH.write_text(json.dumps(state, indent=2))
