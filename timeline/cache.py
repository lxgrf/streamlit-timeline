# timeline/cache.py
import os
import json
from datetime import datetime, timezone
from typing import Dict, List

def _get_cache_path() -> str:
    """Return the file path used for the local snapshot cache."""
    return os.getenv("TIMELINE_CACHE_PATH", ".timeline_model_snapshot.json")

def load_snapshot_from_disk(database_id: str) -> List[Dict] | None:
    """Load cached snapshot of Notion entries from disk if available and matching database_id."""
    cache_path = _get_cache_path()
    try:
        if not os.path.exists(cache_path):
            return None
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if data.get("database_id") != database_id:
            return None
        entries = data.get("all_entries")
        if isinstance(entries, list):
            return entries
        return None
    except Exception:
        return None

def save_snapshot_to_disk(database_id: str, all_entries: List[Dict]) -> None:
    """Persist Notion entries snapshot to disk for reuse across sessions."""
    cache_path = _get_cache_path()
    try:
        payload = {
            "database_id": database_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "all_entries": all_entries,
            "schema_version": 1,
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
    except Exception:
        # Avoid breaking the app on disk I/O issues
        pass