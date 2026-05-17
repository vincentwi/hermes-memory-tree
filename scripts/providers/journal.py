"""Apple Journal source provider — reads HTML entries from Journal.app export."""
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from providers.base import SourceProvider
from models import Document

# Journal entries stored in the app container
JOURNAL_ENTRIES = Path.home() / "Documents" / "AppleJournalEntries" / "Entries"

class JournalProvider(SourceProvider):
    source_id = "journal"

    def __init__(self, entries_path: Path = JOURNAL_ENTRIES):
        self.entries_path = entries_path

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Document]:
        docs = []
        if not self.entries_path.exists():
            return docs
        for html_file in self.entries_path.rglob("*.html"):
            if since:
                mtime = datetime.fromtimestamp(html_file.stat().st_mtime, tz=timezone.utc)
                if mtime <= since:
                    continue
            try:
                raw = html_file.read_text(encoding="utf-8", errors="replace")
                # Strip HTML tags for plain text
                import re
                text = re.sub(r'<[^>]+>', ' ', raw)
                text = re.sub(r'\s+', ' ', text).strip()
                if len(text) < 20:
                    continue
            except (PermissionError, OSError):
                continue
            rel_path = str(html_file.relative_to(self.entries_path)) if self.entries_path in html_file.parents else html_file.name
            docs.append(Document(
                source_id=self.source_id,
                source_path=rel_path,
                content=text,
                title=html_file.stem,
                metadata={"absolute_path": str(html_file)}
            ))
        return docs

    def health_check(self) -> bool:
        return self.entries_path.exists()
