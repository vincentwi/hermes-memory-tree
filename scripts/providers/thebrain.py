"""TheBrain API source provider — fetches thoughts via REST API."""
import json
import time
from datetime import datetime, timezone
from typing import List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from providers.base import SourceProvider
from models import Document
from config import THEBRAIN_API, THEBRAIN_BRAIN_ID, THEBRAIN_API_KEY


class TheBrainProvider(SourceProvider):
    source_id = "brain"

    def __init__(self):
        self.api_key = THEBRAIN_API_KEY
        self.brain_id = THEBRAIN_BRAIN_ID

    def _api_get(self, endpoint: str) -> dict:
        """Make a GET request to TheBrain API."""
        url = f"{THEBRAIN_API}/{endpoint}"
        req = Request(url, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Document]:
        if not self.api_key:
            return []

        docs = []
        try:
            # Get all thoughts (TheBrain API doesn't have a modifiedSince filter easily)
            # We fetch all and filter client-side
            thoughts = self._api_get(f"thoughts/{self.brain_id}")
            time.sleep(2.0)  # Rate limit: ~50 req/min

            for thought in thoughts if isinstance(thoughts, list) else thoughts.get("thoughts", []):
                thought_id = thought.get("id", "")
                name = thought.get("name", "")
                modified = thought.get("modificationDateTime", "")

                if since and modified:
                    try:
                        mod_dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                        if mod_dt <= since:
                            continue
                    except ValueError:
                        pass

                # Build document from thought name + any notes
                content_parts = [f"# {name}"]
                notes = thought.get("notes", "")
                if notes:
                    content_parts.append(notes)

                # Get linked thoughts for context
                content_parts.append(f"\nThought ID: {thought_id}")

                docs.append(Document(
                    source_id=self.source_id,
                    source_path=f"thoughts/{thought_id}",
                    content="\n\n".join(content_parts),
                    title=name,
                    metadata={"thought_id": thought_id}
                ))

                # Respect rate limit
                if len(docs) % 10 == 0:
                    time.sleep(2.0)

        except (URLError, json.JSONDecodeError, KeyError) as e:
            print(f"[thebrain] Error fetching thoughts: {e}")

        return docs

    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            self._api_get("brains")
            return True
        except Exception:
            return False
