import os
import io
import json
import logging
from typing import Optional, Tuple, List
from pathlib import Path

from dotenv import load_dotenv

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    from google.oauth2.service_account import Credentials
except Exception:
    build = None
    MediaFileUpload = None
    MediaIoBaseDownload = None
    Credentials = None

BASE_PATH = Path(__file__).parent.resolve()

class DriveManager:
    """
    Google Drive storage manager using SERVICE ACCOUNT auth only.

    Auth:
      - GDRIVE_SERVICE_ACCOUNT_JSON (inline JSON, recommended on Fly)
      - GDRIVE_SERVICE_ACCOUNT_FILE (local dev only)

    Folder:
      - GDRIVE_FOLDER_ID (preferred, service-account-owned)
      - fallback: GDRIVE_DIR_NAME (search by name)
    """

    def __init__(self):
        load_dotenv()

        self.folder_name = os.getenv("GDRIVE_DIR_NAME") or "XYZBlob"
        self.folder_id = os.getenv("GDRIVE_FOLDER_ID")
        self.drive_id = os.getenv("GDRIVE_DRIVE_ID")
        self.db_folder_id = os.getenv("GDRIVE_DB_FOLDER_ID")

        self.logger = logging.getLogger(__name__)

        self._service = None
        self._creds = None

        if not Credentials or not build:
            self.logger.warning("Google Drive libraries not available")
            return

        try:
            scopes = ["https://www.googleapis.com/auth/drive"]
            inline_json = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON")
            json_path = BASE_PATH / "twiper-service-account.json"

            if inline_json:
                self._creds = Credentials.from_service_account_info(
                    json.loads(inline_json),
                    scopes=scopes,
                )
            elif json_path and os.path.exists(json_path):
                self._creds = Credentials.from_service_account_file(
                    json_path,
                    scopes=scopes,
                )
            else:
                self.logger.warning("No Google Drive credentials found")
                return

            self._service = build("drive", "v3", credentials=self._creds)
            self.logger.info(
                "Google Drive initialized (folder_id=%s, folder_name=%s)",
                self.folder_id,
                self.folder_name,
            )

        except Exception:
            self.logger.exception("Failed to initialize Google Drive client")
            self._service = None

    # ---------- Core ----------
    def ensure_login(self):
        return self._service

    def ensure_login_or_raise(self):
        if not self._service:
            raise RuntimeError("Google Drive not initialized (missing or invalid credentials)")

    # ---------- Helpers ----------
    def _supports_all_drives(self) -> dict:
        if self.drive_id:
            return {
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
                "driveId": self.drive_id,
                "corpora": "drive",
            }
        return {"corpora": "user"}

    def _get_folder_id(self) -> Optional[str]:
        if self.folder_id:
            return self.folder_id

        service = self.ensure_login()
        if not service:
            return None

        try:
            params = {
                "q": (
                    f"name = '{self.folder_name}' "
                    "and mimeType = 'application/vnd.google-apps.folder' "
                    "and trashed = false"
                ),
                "pageSize": 1,
                "fields": "files(id, name)",
            }
            params.update(self._supports_all_drives())
            resp = service.files().list(**params).execute()
            files = resp.get("files", [])
            if files:
                self.folder_id = files[0]["id"]
                return self.folder_id
        except Exception:
            self.logger.debug("Folder lookup failed", exc_info=True)

        return None

    def _get_db_folder_id(self) -> Optional[str]:
        if self.db_folder_id:
            return self.db_folder_id
        return None

    # ---------- Upload ----------
    def upload_or_replace_file(self, local_path: str, remote_name: Optional[str] = None) -> None:
        self.ensure_login_or_raise()

        folder_id = self._get_folder_id()
        remote_name = remote_name or os.path.basename(local_path)

        try:
            if folder_id:
                dupes = self._list_nodes_in_folder_by_name(remote_name)
                for fid, _ in dupes:
                    self._service.files().delete(
                        fileId=fid,
                        supportsAllDrives=bool(self.drive_id),
                    ).execute()

            media = MediaFileUpload(local_path, resumable=True)
            metadata = {"name": remote_name}
            if folder_id:
                metadata["parents"] = [folder_id]

            self._service.files().create(
                body=metadata,
                media_body=media,
                supportsAllDrives=bool(self.drive_id),
            ).execute()

            self.logger.info("Uploaded file to Drive: %s", remote_name)

        except Exception:
            self.logger.exception("Drive upload failed: %s", local_path)
            raise

    def upload_or_replace_db_file(self, local_path: str, remote_name: Optional[str] = None) -> None:
        self.ensure_login_or_raise()
        folder_id = self._get_db_folder_id() or self._get_folder_id()
        remote_name = remote_name or os.path.basename(local_path)
        try:
            if folder_id:
                dupes = self._list_nodes_in_folder_by_name(remote_name, folder_id=folder_id)
                for fid, _ in dupes:
                    try:
                        self._service.files().delete(
                            fileId=fid,
                            supportsAllDrives=bool(self.drive_id),
                        ).execute()
                    except Exception:
                        # Non-fatal: if we lack permission to delete existing files, still proceed to create new file
                        self.logger.debug("Skipping delete for existing DB file id=%s due to permissions", fid, exc_info=True)

            media = MediaFileUpload(local_path, resumable=True)
            metadata = {"name": remote_name}
            if folder_id:
                metadata["parents"] = [folder_id]

            self._service.files().create(
                body=metadata,
                media_body=media,
                supportsAllDrives=bool(self.drive_id),
            ).execute()
            self.logger.info("Uploaded DB file to Drive: %s", remote_name)
        except Exception:
            self.logger.exception("Drive DB upload failed: %s", local_path)
            raise

    # ---------- Download ----------
    def download_video(
        self,
        dest_dir: str,
        file_name: Optional[str] = None,
        public_url: Optional[str] = None,
    ) -> Tuple[str, Optional[object]]:

        self.ensure_login_or_raise()
        os.makedirs(dest_dir, exist_ok=True)

        if public_url:
            file_id = self._extract_file_id(public_url)
            if not file_id:
                raise FileNotFoundError("Invalid Google Drive URL")
            path = self._download_file_by_id(file_id, None, dest_dir)
            return path, (file_id, None)

        if file_name:
            node = self.find_file(file_name)
        else:
            node = self._get_latest_video_node()

        if not node:
            raise FileNotFoundError("No video found in Drive")

        path = self._download_file_by_id(node["id"], node["name"], dest_dir)
        return path, (node["id"], node["name"])

    # ---------- Remaining methods ----------
    def _iter_children(self, parent_id: str) -> List[dict]:
        service = self.ensure_login()
        if not service:
            return []
        items: List[dict] = []
        page_token = None
        try:
            while True:
                params = {
                    "q": f"'{parent_id}' in parents and trashed = false",
                    "fields": "nextPageToken, files(id, name, mimeType, parents, createdTime, modifiedTime)",
                    "pageSize": 1000,
                }
                params.update(self._supports_all_drives())
                if page_token:
                    params["pageToken"] = page_token
                resp = service.files().list(**params).execute()
                items.extend(resp.get("files", []))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except Exception:
            self.logger.debug("List children failed for parent=%s", parent_id, exc_info=True)
        return items

    def _walk_folder_tree(self, root_id: str) -> List[dict]:
        result: List[dict] = []
        queue: List[str] = [root_id]
        service = self.ensure_login()
        if not service:
            return result
        seen: set[str] = set()
        while queue:
            pid = queue.pop(0)
            if pid in seen:
                continue
            seen.add(pid)
            children = self._iter_children(pid)
            for item in children:
                result.append(item)
                if item.get("mimeType") == "application/vnd.google-apps.folder":
                    queue.append(item["id"])
        return result

    def _list_nodes_in_folder_by_name(self, name: str, folder_id: Optional[str] = None):
        service = self.ensure_login()
        if not service:
            return []
        folder_id = folder_id or self._get_folder_id()
        if not folder_id:
            return []
        items = self._walk_folder_tree(folder_id)
        candidates = []
        for it in items:
            if it.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            if (it.get("name") or "") == name:
                ts = it.get("modifiedTime") or it.get("createdTime") or ""
                candidates.append((ts, it["id"], it))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [(fid, meta) for _, fid, meta in candidates]

    def find_file(self, name: str):
        service = self.ensure_login()
        if not service:
            return None
        try:
            params = {
                "q": f"name = '{name}' and trashed = false",
                "pageSize": 1,
                "fields": "files(id, name, mimeType, parents, createdTime, modifiedTime)",
            }
            params.update(self._supports_all_drives())
            resp = service.files().list(**params).execute()
            files = resp.get("files", [])
            return files[0] if files else None
        except Exception:
            return None

    def _download_file_by_id(self, file_id: str, name: Optional[str], dest_dir: str) -> str:
        service = self.ensure_login()
        if not service:
            raise RuntimeError("Google Drive credentials missing")
        request = service.files().get_media(fileId=file_id, supportsAllDrives=bool(self.drive_id))
        fname = name or f"{file_id}.bin"
        local_path = os.path.join(dest_dir, fname)
        fh = io.FileIO(local_path, "wb")
        downloader = MediaIoBaseDownload(fh, request)
        try:
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    self.logger.info("Drive download progress: %.1f%%", status.progress() * 100)
        finally:
            fh.close()
        return local_path

    def _get_latest_video_node(self):
        service = self.ensure_login()
        if not service:
            return None
        folder_id = self._get_folder_id()
        if not folder_id:
            return None
        items = self._walk_folder_tree(folder_id)
        best = None
        best_ts = ""
        for it in items:
            if (it.get("mimeType") or "").startswith("video/"):
                ts = it.get("modifiedTime") or it.get("createdTime") or ""
                if ts and ts > best_ts:
                    best_ts = ts
                    best = it
        if best:
            self.logger.info("Latest Drive video in %s: %s (ts=%s)", self.folder_name, best.get("name"), best_ts)
        return best

    def list_recent_videos(self, limit: int | None = None):
        service = self.ensure_login()
        if not service:
            return []
        folder_id = self._get_folder_id()
        if not folder_id:
            return []
        items = self._walk_folder_tree(folder_id)
        videos = []
        for it in items:
            if (it.get("mimeType") or "").startswith("video/"):
                ts = it.get("modifiedTime") or it.get("createdTime") or ""
                videos.append((ts, it.get("id"), it.get("name")))
        videos.sort(key=lambda x: x[0], reverse=True)
        results = [(h, n, t) for t, h, n in videos]
        if limit and limit > 0:
            return results[:limit]
        return results

    def delete(self, node: Optional[object]) -> None:
        if node is None:
            return
        service = self.ensure_login()
        if not service:
            return
        file_id = None
        name = None

        def extract(obj):
            if obj is None:
                return None, None
            try:
                if isinstance(obj, str):
                    return obj, None
                if isinstance(obj, tuple) and len(obj) >= 1:
                    first = obj[0]
                    second = obj[1] if len(obj) > 1 else None
                    if isinstance(first, str):
                        return first, second if isinstance(second, str) else None
                if isinstance(obj, dict):
                    return obj.get("id"), obj.get("name")
            except Exception:
                return None, None
            return None, None

        file_id, name = extract(node)
        if not file_id and name:
            try:
                found = self.find_file(name)
                if found:
                    file_id = found.get("id")
            except Exception:
                pass

        if not file_id:
            self.logger.warning("Cannot delete Drive node: unknown id from %r", type(node))
            return

        try:
            service.files().update(
                fileId=file_id,
                body={"trashed": True},
                supportsAllDrives=bool(self.drive_id),
            ).execute()
            self.logger.info("Moved Drive file to trash (id=%s)", file_id)
        except Exception:
            self.logger.warning("Failed to move Drive file to trash id=%s", file_id, exc_info=True)

    def _extract_file_id(self, url: str) -> Optional[str]:
        try:
            import re
            m = re.search(r"/d/([A-Za-z0-9_-]+)", url)
            if m:
                return m.group(1)
            m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
            if m:
                return m.group(1)
        except Exception:
            pass
        return None

    def download_file_by_name(self, name: str, dest_dir: str) -> Optional[str]:
        self.ensure_login_or_raise()
        os.makedirs(dest_dir, exist_ok=True)
        matches = self._list_nodes_in_folder_by_name(name)
        if not matches:
            return None
        file_id, meta = matches[0]
        return self._download_file_by_id(file_id, meta.get("name"), dest_dir)

    def download_db_file_by_name(self, name: str, dest_dir: str) -> Optional[str]:
        self.ensure_login_or_raise()
        os.makedirs(dest_dir, exist_ok=True)
        folder_id = self._get_db_folder_id() or self._get_folder_id()
        if not folder_id:
            return None
        matches = self._list_nodes_in_folder_by_name(name, folder_id=folder_id)
        if not matches:
            return None
        file_id, meta = matches[0]
        return self._download_file_by_id(file_id, meta.get("name"), dest_dir)
