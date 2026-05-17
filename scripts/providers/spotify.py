"""Spotify streaming history provider — reads extended streaming JSON."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from providers.base import SourceProvider
from models import Document

SPOTIFY_DIR = Path.home() / "Downloads" / "Spotify Extended Streaming History 2"

class SpotifyProvider(SourceProvider):
    source_id = "spotify"

    def __init__(self, data_dir: Path = SPOTIFY_DIR):
        self.data_dir = data_dir

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Document]:
        docs = []
        if not self.data_dir.exists():
            return docs
        for json_file in sorted(self.data_dir.glob("Streaming_History_Audio_*.json")):
            try:
                entries = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            # Group entries by date for chunking
            by_date = {}
            for entry in entries:
                ts = entry.get("ts", "")
                date_key = ts[:7] if ts else "unknown"  # Group by month (YYYY-MM)
                if since and ts:
                    try:
                        entry_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if entry_dt <= since:
                            continue
                    except ValueError:
                        pass
                by_date.setdefault(date_key, []).append(entry)
            
            for date_key, day_entries in by_date.items():
                # Sort by play duration, keep top 50 most-played per month
                day_entries.sort(key=lambda e: e.get("ms_played", 0), reverse=True)
                top = day_entries[:50]
                lines = [f"# Spotify Listening — {date_key}\n"]
                lines.append(f"Total tracks: {len(day_entries)}, showing top {len(top)} by play time\n")
                for e in top:
                    artist = e.get("master_metadata_album_artist_name", "Unknown")
                    track = e.get("master_metadata_track_name", "Unknown")
                    album = e.get("master_metadata_album_album_name", "")
                    ms = e.get("ms_played", 0)
                    mins = ms // 60000
                    reason_start = e.get("reason_start", "")
                    reason_end = e.get("reason_end", "")
                    lines.append(f"- {artist} — {track} ({album}) [{mins}m] start={reason_start} end={reason_end}")
                
                content = "\n".join(lines)
                docs.append(Document(
                    source_id=self.source_id,
                    source_path=f"{json_file.name}/{date_key}",
                    content=content,
                    title=f"Spotify {date_key}",
                    metadata={"date": date_key, "track_count": len(day_entries)}
                ))
        return docs

    def health_check(self) -> bool:
        return self.data_dir.exists() and any(self.data_dir.glob("*.json"))
