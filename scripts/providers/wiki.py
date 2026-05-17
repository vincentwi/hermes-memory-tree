"""LLM Wiki source provider — reads .md files from ~/llm-wiki/."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from providers.base import SourceProvider
from models import Document
from config import LLM_WIKI


class WikiProvider(SourceProvider):
    source_id = "wiki"

    def __init__(self, wiki_path: Path = LLM_WIKI):
        self.wiki_path = wiki_path

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Document]:
        docs = []
        if since and (self.wiki_path / ".git").exists():
            # Use git to find changed files
            since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
            try:
                result = subprocess.run(
                    ["git", "diff", "--name-only", f"--diff-filter=ACMR",
                     f"HEAD@{{{since_str}}}"],
                    cwd=str(self.wiki_path), capture_output=True, text=True, timeout=10
                )
                changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip().endswith(".md")]
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                changed_files = []
                # Fallback: check mtimes
                for md_file in self.wiki_path.rglob("*.md"):
                    mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=timezone.utc)
                    if mtime > since:
                        changed_files.append(str(md_file.relative_to(self.wiki_path)))
        else:
            changed_files = [str(f.relative_to(self.wiki_path)) for f in self.wiki_path.rglob("*.md")]

        for rel_path in changed_files:
            full_path = self.wiki_path / rel_path
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            docs.append(Document(
                source_id=self.source_id,
                source_path=rel_path,
                content=content,
                title=full_path.stem
            ))
        return docs

    def health_check(self) -> bool:
        return self.wiki_path.exists()
