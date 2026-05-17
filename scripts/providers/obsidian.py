"""Obsidian Vault source provider — reads .md files from the vault."""
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from providers.base import SourceProvider
from models import Document
from config import OBSIDIAN_VAULT


class ObsidianProvider(SourceProvider):
    source_id = "obsidian"

    def __init__(self, vault_path: Path = OBSIDIAN_VAULT):
        self.vault_path = vault_path

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Document]:
        docs = []
        for md_file in self.vault_path.rglob("*.md"):
            # Skip .obsidian config directory
            if ".obsidian" in str(md_file):
                continue
            if since:
                mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=timezone.utc)
                if mtime <= since:
                    continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            rel_path = str(md_file.relative_to(self.vault_path))
            docs.append(Document(
                source_id=self.source_id,
                source_path=rel_path,
                content=content,
                title=md_file.stem,
                metadata={"absolute_path": str(md_file)}
            ))
        return docs

    def health_check(self) -> bool:
        return self.vault_path.exists() and self.vault_path.is_dir()
