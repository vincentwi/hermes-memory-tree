"""Hermes chat history provider — reads session transcripts."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from providers.base import SourceProvider
from models import Document

HERMES_STATE_DB = Path.home() / ".hermes" / "state.db"


class ChatProvider(SourceProvider):
    source_id = "chat"

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Document]:
        docs = []
        if not HERMES_STATE_DB.exists():
            return docs

        try:
            conn = sqlite3.connect(str(HERMES_STATE_DB), timeout=10)
            conn.row_factory = sqlite3.Row

            query = "SELECT id, title, started_at FROM sessions ORDER BY started_at DESC LIMIT 50"
            if since:
                since_epoch = since.timestamp()
                query = f"SELECT id, title, started_at FROM sessions WHERE started_at > {since_epoch} ORDER BY started_at DESC LIMIT 50"

            rows = conn.execute(query).fetchall()
            for row in rows:
                title = row["title"] or "Untitled Session"
                session_id = row["id"]
                # Try to get first few messages for content
                msgs = conn.execute(
                    "SELECT content FROM messages WHERE session_id = ? AND role = 'assistant' ORDER BY rowid LIMIT 3",
                    (session_id,)
                ).fetchall()
                preview = "\n\n".join(m["content"][:500] for m in msgs if m["content"]) if msgs else ""
                docs.append(Document(
                    source_id=self.source_id,
                    source_path=f"sessions/{session_id}",
                    content=f"# {title}\n\n{preview}",
                    title=title
                ))
            conn.close()
        except (sqlite3.Error, KeyError) as e:
            print(f"[chat] Error reading sessions: {e}")
        return docs

    def health_check(self) -> bool:
        return HERMES_STATE_DB.exists()
