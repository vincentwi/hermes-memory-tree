"""Apple Notes source provider — uses osascript to access Notes.app."""
import subprocess
import re
from datetime import datetime, timezone
from typing import List, Optional
from providers.base import SourceProvider
from models import Document


class AppleNotesProvider(SourceProvider):
    source_id = "apple-notes"

    # Delimiter unlikely to appear in note content
    _DELIM = "|||HERMES_SEP|||"

    def _run_osascript(self, script: str, timeout: int = 60) -> str:
        """Run an AppleScript via osascript and return stdout."""
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Document]:
        docs: List[Document] = []
        try:
            # Get note names, bodies, and ids via AppleScript
            # We fetch them as delimited strings to parse reliably
            script = f'''
tell application "Notes"
    set noteList to every note
    set output to ""
    repeat with n in noteList
        set noteName to name of n
        set noteID to id of n
        set noteBody to plaintext of n
        -- Replace newlines in body to keep one-line-per-note
        set AppleScript's text item delimiters to return
        set bodyParts to text items of noteBody
        set AppleScript's text item delimiters to "\\n"
        set cleanBody to bodyParts as text
        set AppleScript's text item delimiters to ""
        set output to output & noteName & "{self._DELIM}" & cleanBody & "{self._DELIM}" & noteID & linefeed
    end repeat
    return output
end tell
'''
            raw = self._run_osascript(script, timeout=120)
            for line in raw.split("\n"):
                line = line.strip()
                if not line:
                    continue
                parts = line.split(self._DELIM)
                if len(parts) < 3:
                    continue
                title = parts[0].strip()
                body = parts[1].strip().replace("\\n", "\n")
                note_id = parts[2].strip()

                content = body if body else title
                if not content:
                    continue

                docs.append(Document(
                    source_id=self.source_id,
                    source_path=note_id,
                    content=content,
                    title=title or "Untitled",
                ))
        except (subprocess.TimeoutExpired, FileNotFoundError, RuntimeError):
            pass
        return docs

    def health_check(self) -> bool:
        try:
            count_str = self._run_osascript(
                'tell application "Notes" to get count of every note',
                timeout=10
            )
            return count_str.isdigit() and int(count_str) > 0
        except Exception:
            return False
