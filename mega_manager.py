import os
import logging
import re
import sys
import shutil
from typing import Optional, Tuple

from dotenv import load_dotenv

try:
	from mega import Mega
except Exception as e:
	Mega = None  # Will surface a clearer error at runtime


class MegaManager:
	def __init__(self):
		load_dotenv()
		self.email = os.getenv("MEGA_EMAIL")
		self.password = os.getenv("MEGA_PASSWORD")
		# Allow override via env, default to requested folder name
		self.folder_name = os.getenv("MEGA_DIR_NAME") or "XYZBlob"
		self._mega = Mega() if Mega else None
		self._session = None
		self.logger = logging.getLogger(__name__)

		if self.email and self.password and self._mega:
			self._session = self._mega.login(self.email, self.password)
			self.logger.info("Logged in to MEGA. folder=%s", self.folder_name)
		else:
			self.logger.info("MEGA login skipped (public URL mode or missing creds). folder=%s", self.folder_name)

		# Improve visual progress for mega.mega logger by installing a custom handler
		if (os.getenv("MEGA_PROGRESS_BAR") or "1").lower() in {"1", "true", "yes"}:
			try:
				self._attach_mega_progress_handler()
			except Exception:
				# Non-fatal: keep default logging if progress handler fails
				self.logger.debug("Progress handler attach failed", exc_info=True)

	def _attach_mega_progress_handler(self):
		mega_logger = logging.getLogger("mega.mega")
		# Remove existing handlers to avoid duplicate lines
		for h in list(mega_logger.handlers):
			mega_logger.removeHandler(h)
		mega_logger.propagate = False
		mega_logger.setLevel(logging.INFO)
		mega_logger.addHandler(_MegaProgressHandler())

	def ensure_login(self):
		if self._session is None and self.email and self.password and self._mega:
			self._session = self._mega.login(self.email, self.password)
			self.logger.debug("MEGA session established on demand")
		return self._session

	def download_video(self, dest_dir: str, file_name: Optional[str] = None, public_url: Optional[str] = None) -> Tuple[str, Optional[object]]:
		"""
		Download a video either via public URL or by filename from the account.
		Returns (local_path, node_for_delete).
		"""
		if self._mega is None:
			raise RuntimeError("mega.py not installed. Run 'pip install mega.py'.")

		os.makedirs(dest_dir, exist_ok=True)

		if public_url:
			self.logger.info("Downloading MEGA file from public URL into %s", dest_dir)
			local_path = self._mega.download_url(public_url, dest_dir)
			# Try to resolve node by filename if logged in (optional)
			node = None
			basename = os.path.basename(local_path)
			if self.ensure_login():
				try:
					node = self._session.find(basename)
				except Exception:
					node = None
			self.logger.info("Downloaded public URL to %s", local_path)
			# Return a tuple token (handle, name) if possible, else None
			return local_path, self._to_delete_token(node)

		# Account-based download by filename
		session = self.ensure_login()
		if not session:
			raise RuntimeError("MEGA credentials missing; set MEGA_EMAIL and MEGA_PASSWORD or provide MEGA_PUBLIC_URL")

		# If a specific file name isn't provided, pick the latest video
		if not file_name:
			self.logger.info("Selecting latest video from MEGA folder: %s", self.folder_name)
			node = self._get_latest_video_node()
			if node is None:
				raise FileNotFoundError("No video files found in MEGA account")
		else:
			self.logger.info("Selecting specific MEGA file: %s", file_name)
			node = session.find(file_name)
			if node is None:
				raise FileNotFoundError(f"MEGA file not found: {file_name}")

		local_path = session.download(node, dest_dir)
		self.logger.info("Downloaded MEGA file to %s", local_path)
		return local_path, self._to_delete_token(node)

	def _get_latest_video_node(self):
		"""Return the most recent video node from the configured folder (default 'XYZBlob')."""
		session = self.ensure_login()
		if not session:
			return None
		try:
			files = session.get_files()
		except Exception:
			files = None

		candidates = []
		video_exts = (".mp4", ".mov", ".mkv", ".webm")

		# Compute the set of node IDs under the target folder (including nested)
		allowed_parents = None
		folder_node = None
		try:
			folder_node = session.find(self.folder_name)
		except Exception:
			folder_node = None

		if isinstance(files, dict):
			if folder_node and isinstance(folder_node, dict):
				folder_id = folder_node.get("h")
			else:
				# Try alternative attribute access for folder handle
				try:
					folder_id = getattr(folder_node, "h", None)
				except Exception:
					folder_id = None

			if folder_id:
				allowed_parents = {folder_id}
				# Build parent -> children mapping
				parent_map = {}
				for nid, meta in files.items():
					p = meta.get("p")
					if p:
						parent_map.setdefault(p, []).append(nid)
				# BFS to include nested folder contents
				queue = [folder_id]
				while queue:
					pid = queue.pop(0)
					for child in parent_map.get(pid, []):
						allowed_parents.add(child)
						# If child is a folder (t == 1), continue traversing
						child_meta = files.get(child, {})
						if child_meta.get("t") == 1:
							queue.append(child)

			# Collect candidate video files within allowed parents set (or globally if folder missing)
			for nid, meta in files.items():
				name = (meta.get("a") or {}).get("n") or ""
				if not name or not name.lower().endswith(video_exts):
					continue
				parent_id = meta.get("p")
				if allowed_parents and parent_id not in allowed_parents:
					continue
				ts = meta.get("ts") or meta.get("c") or 0
				try:
					ts_val = int(ts)
				except Exception:
					ts_val = 0
				candidates.append((ts_val, name))

		if not candidates:
			return None

		candidates.sort(key=lambda x: x[0], reverse=True)
		latest_ts, latest_name = candidates[0]
		self.logger.info("Latest MEGA video in %s: %s (ts=%s)", self.folder_name, latest_name, latest_ts)
		try:
			return session.find(latest_name)
		except Exception:
			return None

	def list_recent_videos(self, limit: int | None = None):
		"""Return a list of (handle, name, ts) for videos in the configured folder, newest first."""
		session = self.ensure_login()
		if not session:
			return []
		try:
			files = session.get_files()
		except Exception:
			files = None

		video_exts = (".mp4", ".mov", ".mkv", ".webm")
		allowed_parents = None
		folder_node = None
		try:
			folder_node = session.find(self.folder_name)
		except Exception:
			folder_node = None

		if isinstance(files, dict):
			if folder_node and isinstance(folder_node, dict):
				folder_id = folder_node.get("h")
			else:
				try:
					folder_id = getattr(folder_node, "h", None)
				except Exception:
					folder_id = None

			if folder_id:
				allowed_parents = {folder_id}
				parent_map = {}
				for nid, meta in files.items():
					p = meta.get("p")
					if p:
						parent_map.setdefault(p, []).append(nid)
				queue = [folder_id]
				while queue:
					pid = queue.pop(0)
					for child in parent_map.get(pid, []):
						allowed_parents.add(child)
						child_meta = files.get(child, {})
						if child_meta.get("t") == 1:
							queue.append(child)

			candidates = []
			for nid, meta in files.items():
				name = (meta.get("a") or {}).get("n") or ""
				if not name or not name.lower().endswith(video_exts):
					continue
				parent_id = meta.get("p")
				if allowed_parents and parent_id not in allowed_parents:
					continue
				ts = meta.get("ts") or meta.get("c") or 0
				try:
					ts_val = int(ts)
				except Exception:
					ts_val = 0
				handle = nid
				candidates.append((ts_val, handle, name))

			candidates.sort(key=lambda x: x[0], reverse=True)
			items = [(h, n, t) for t, h, n in candidates]
			return items[:limit] if limit else items

		return []

	def delete(self, node: Optional[object]) -> None:
		if node is None:
			return
		# Extract node id/handle accepted by mega.py
		node_id = None
		possible_name = None

		def extract_from_obj(obj):
			try:
				if isinstance(obj, str):
					# Heuristic: MEGA handles are base64-like, length >=6
					return obj if len(obj) >= 6 else None
				sel_obj = obj
				if isinstance(sel_obj, dict):
					# Save potential filename for fallback find
					name = (sel_obj.get("a") or {}).get("n") or sel_obj.get("name")
					return sel_obj.get("h") or sel_obj.get("handle") or name
				# Generic attribute access
				h = getattr(sel_obj, "h", None)
				if h:
					return h
				name = getattr(sel_obj, "name", None)
				return name
			except Exception:
				return None

		# Direct extraction
		val = extract_from_obj(node)
		if isinstance(val, str):
			node_id = val
		else:
			possible_name = val if isinstance(val, str) else None

		# Tuple form: scan parts for handle first, name second
		if node_id is None and isinstance(node, tuple):
			for part in node:
				val = extract_from_obj(part)
				if isinstance(val, str) and len(val) >= 6:
					node_id = val
					break
				if possible_name is None and isinstance(val, str):
					possible_name = val

		# Fallback: if we only got a name, resolve to handle
		if node_id is None and possible_name and self._session:
			try:
				found = self._session.find(possible_name)
				extracted = extract_from_obj(found)
				if isinstance(extracted, str) and len(extracted) >= 6:
					node_id = extracted
			except Exception:
				pass

		if not node_id:
			self.logger.warning("Cannot delete MEGA node: unknown handle from %r", type(node))
			return

		try:
			if (os.getenv("MEGA_HARD_DELETE") or "0").lower() in {"1", "true", "yes"}:
				self._session.destroy(node_id)
				self.logger.info("Destroyed MEGA file (node_id=%s)", node_id)
			else:
				self._session.delete(node_id)
				self.logger.info("Deleted MEGA file (node_id=%s)", node_id)
			# Verify presence after operation
			try:
				files = self._session.get_files()
				if isinstance(files, dict) and node_id in files:
					self.logger.warning("MEGA node still present after delete: node_id=%s", node_id)
			except Exception:
				pass
		except Exception:
			# Swallow delete errors to avoid blocking post flow
			self.logger.warning("Failed to delete MEGA node_id=%s", node_id, exc_info=True)

	def _to_delete_token(self, node: Optional[object]) -> Optional[object]:
		"""Return a deletion token for a node (prefer (handle, name) tuple)."""
		if node is None:
			return None
		name = None
		handle = None
		try:
			if isinstance(node, dict):
				name = (node.get("a") or {}).get("n") or node.get("name")
				handle = node.get("h") or node.get("handle")
			else:
				name = getattr(node, "name", None)
				handle = getattr(node, "h", None)
		except Exception:
			pass
		# If we have neither, just return the node and let delete() try its best
		if not handle and not name:
			return node
		return (handle or "", name or "")


class _MegaProgressHandler(logging.Handler):
	"""Transforms mega.mega progress logs into a single-line progress bar."""
	_pattern = re.compile(r"(\d+) of (\d+) downloaded")

	def emit(self, record: logging.LogRecord) -> None:
		try:
			msg = record.getMessage()
			m = self._pattern.search(msg)
			if not m:
				return
			cur = int(m.group(1))
			total = int(m.group(2)) if int(m.group(2)) > 0 else 1
			pct = cur / total
			width = shutil.get_terminal_size((80, 20)).columns
			bar_width = max(10, min(40, width - 40))
			filled = int(bar_width * pct)
			bar = "[" + "#" * filled + "-" * (bar_width - filled) + "]"
			text = f"\rMEGA Download {bar} {pct*100:5.1f}% ({cur/1048576:.1f}/{total/1048576:.1f} MiB)"
			sys.stdout.write(text)
			sys.stdout.flush()
			if cur >= total:
				sys.stdout.write("\n")
				sys.stdout.flush()
		except Exception:
			# Never fail logging
			pass
