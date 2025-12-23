import os
import sqlite3
import threading
import time
from typing import Optional
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class DBManager:
	def __init__(self, db_path: str = BASE_DIR / "twiper.db"):
		self.db_path = db_path
		# os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
		self._lock = threading.Lock()
		self._init_schema()

	def _connect(self):
		return sqlite3.connect(self.db_path)

	def _init_schema(self):
		with self._connect() as conn:
			c = conn.cursor()
			c.execute(
				"""
				CREATE TABLE IF NOT EXISTS posted_media (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					source TEXT NOT NULL,
					handle TEXT,
					name TEXT,
					tweet_id TEXT,
					posted_at INTEGER NOT NULL
				);
				"""
			)
			c.execute(
				"""
				CREATE UNIQUE INDEX IF NOT EXISTS idx_posted_unique
				ON posted_media (source, COALESCE(handle, ''), COALESCE(name, ''));
				"""
			)
			conn.commit()

	def is_posted(self, source: str, handle: Optional[str], name: Optional[str]) -> bool:
		with self._lock, self._connect() as conn:
			c = conn.cursor()
			c.execute(
				"""
				SELECT 1 FROM posted_media
				WHERE source = ? AND COALESCE(handle,'') = COALESCE(?, '') AND COALESCE(name,'') = COALESCE(?, '')
				LIMIT 1
				""",
				(source, handle, name),
			)
			return c.fetchone() is not None

	def mark_posted(self, source: str, handle: Optional[str], name: Optional[str], tweet_id: Optional[str]) -> None:
		# Sanitize inputs to avoid non-serializable types (e.g., dicts)
		if not isinstance(handle, (str, type(None))):
			handle = None
		if not isinstance(name, (str, type(None))):
			name = None
		with self._lock, self._connect() as conn:
			c = conn.cursor()
			try:
				c.execute(
					"""
					INSERT OR IGNORE INTO posted_media (source, handle, name, tweet_id, posted_at)
					VALUES (?,?,?,?,?)
					""",
					(source, handle, name, tweet_id or None, int(time.time())),
				)
				conn.commit()
			except sqlite3.Error:
				conn.rollback()
				raise

	# Convenience wrappers for MEGA
	def is_mega_posted(self, handle: Optional[str], name: Optional[str]) -> bool:
		return self.is_posted("MEGA", handle, name)

	def mark_mega_posted(self, handle: Optional[str], name: Optional[str], tweet_id: Optional[str]) -> None:
		self.mark_posted("MEGA", handle, name, tweet_id)
