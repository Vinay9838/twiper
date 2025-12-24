import json
import os
import threading
from pathlib import Path
from typing import Optional, Set


class JsonDBManager:
    """
    Minimal JSON-based tracker for posted MEGA filenames.

    - Stores only filenames (strings) in a JSON array.
    - Can sync the JSON file from/to the configured MEGA folder.
    """

    def __init__(self, json_path: str | Path = Path("data") / "posted.json"):
        self.json_path = Path(json_path)
        self._lock = threading.Lock()
        self._posted: Set[str] = set()
        # Ensure parent directory exists
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        # Load from local if present; otherwise start empty
        try:
            if self.json_path.is_file():
                self._posted = set(self._read_local())
        except Exception:
            # Non-fatal: start with empty set
            self._posted = set()

    # ---------- Local file I/O ----------

    def _read_local(self) -> list[str]:
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data if isinstance(x, (str, int))]
        return []

    def _write_local(self) -> None:
        tmp_path = self.json_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(sorted(self._posted), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)

    # ---------- Public API ----------

    def is_mega_posted(self, name: Optional[str]) -> bool:
        if not isinstance(name, str) or not name:
            return False
        with self._lock:
            return name in self._posted

    def mark_mega_posted(self, name: Optional[str]) -> None:
        if not isinstance(name, str) or not name:
            return
        with self._lock:
            if name not in self._posted:
                self._posted.add(name)
                self._write_local()

    # ---------- MEGA sync ----------

    def sync_from_mega(self, mega_manager) -> bool:
        """
        Download `posted.json` from the MEGA folder into local `json_path`.
        Returns True if a remote file was found and synced; False otherwise.
        """
        try:
            local = mega_manager.download_file_by_name(self.json_path.name, str(self.json_path.parent))
            if local and Path(local).is_file():
                with self._lock:
                    self._posted = set(self._read_local())
                return True
            return False
        except Exception:
            return False

    def sync_to_mega(self, mega_manager, delete_local: bool = True) -> bool:
        """
        Upload/replace `posted.json` to the MEGA folder.
        Returns True on success; False otherwise.
        """
        try:
            # Ensure latest local state is written before upload
            with self._lock:
                self._write_local()
            mega_manager.upload_or_replace_file(str(self.json_path), remote_name=self.json_path.name)
            # Optionally remove local copy to keep MEGA as source of truth
            if delete_local:
                try:
                    os.remove(self.json_path)
                except OSError:
                    pass
            return True
        except Exception:
            return False
