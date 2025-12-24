import aiohttp
import asyncio
import glob
import os
import logging
import sys
from typing import List, Optional

from dotenv import load_dotenv
from oauthlib.oauth1 import Client

from app.media_manager import XVideoUploader, UPLOAD_URL
from app.mega_manager import MegaManager
from .db_manager import DBManager

TWEETS_URL = "https://api.twitter.com/2/tweets"


class XTweetManager:
	def __init__(self):
		load_dotenv()
		self.logger = logging.getLogger(__name__)

		# Resolve credentials from common environment aliases
		def _get_env_any(*keys: str) -> Optional[str]:
			for k in keys:
				v = os.getenv(k)
				if v:
					return v
			return None

		self._api_key = _get_env_any("X_API_KEY", "TWITTER_API_KEY", "CONSUMER_KEY")
		self._api_secret = _get_env_any("X_API_SECRET", "TWITTER_API_SECRET", "CONSUMER_SECRET")
		self._access_token = _get_env_any("X_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN")
		self._access_secret = _get_env_any("X_ACCESS_SECRET", "TWITTER_ACCESS_SECRET")

		missing = []
		if not self._api_key:
			missing.append("API key")
		if not self._api_secret:
			missing.append("API secret")
		if not self._access_token:
			missing.append("Access token")
		if not self._access_secret:
			missing.append("Access secret")
		if missing:
			raise RuntimeError(f"Missing OAuth credentials: {', '.join(missing)}")

		self.client = Client(
			client_key=self._api_key,
			client_secret=self._api_secret,
			resource_owner_key=self._access_token,
			resource_owner_secret=self._access_secret,
			signature_type="AUTH_HEADER",
		)

		self.video_uploader = XVideoUploader()
		self.mega = MegaManager()
		self.db = DBManager(os.getenv("DB_PATH") or os.path.join("data", "twiper.db"))
		self.logger.debug("XTweetManager initialized")

	def sign_json(self, method: str, url: str) -> dict:
		_, headers, _ = self.client.sign(uri=url, http_method=method)
		headers["Content-Type"] = "application/json"
		return headers

	def sign_multipart(self, method: str) -> dict:
		_, headers, _ = self.client.sign(uri=UPLOAD_URL, http_method=method)
		return headers

	async def upload_image(self, path: str) -> str:
		if not os.path.isfile(path):
			raise FileNotFoundError(path)

		async with aiohttp.ClientSession() as session:
			form = aiohttp.FormData()
			with open(path, "rb") as fh:
				form.add_field("media", fh, filename=os.path.basename(path))

				async with session.post(
					UPLOAD_URL,
					data=form,
					headers=self.sign_multipart("POST"),
				) as r:
					r.raise_for_status()
					result = await r.json()
					media_id = result["media_id_string"]
					self.logger.info("Image uploaded: path=%s media_id=%s", path, media_id)
					return media_id

	async def create_tweet(self, text: Optional[str], media_ids: Optional[List[str]]) -> dict:
		payload = {}
		if text:
			payload["text"] = text
		if media_ids:
			payload["media"] = {"media_ids": media_ids}

		async with aiohttp.ClientSession() as session:
			self.logger.info(
				"Creating tweet: text_len=%s media_count=%s",
				(len(text) if text else 0),
				(len(media_ids) if media_ids else 0),
			)
			async with session.post(
				TWEETS_URL,
				json=payload,
				headers=self.sign_json("POST", TWEETS_URL),
			) as r:
				r.raise_for_status()
				resp = await r.json()
				tweet_id = (resp.get("data") or {}).get("id")
				if tweet_id:
					self.logger.info("Tweet created: id=%s", tweet_id)
				else:
					self.logger.info("Tweet created (no id in response)")
				return resp

	async def post_from_dir(self, data_dir: str = "data") -> dict:
		txt_files = sorted(glob.glob(os.path.join(data_dir, "*.txt")))
		text = None
		if txt_files:
			with open(txt_files[0], "r", encoding="utf-8") as f:
				text = f.read().strip()

		image_patterns = ["*.jpg", "*.jpeg", "*.png", "*.gif"]
		image_paths: List[str] = []
		for p in image_patterns:
			image_paths += glob.glob(os.path.join(data_dir, p))
		image_paths = sorted(image_paths)

		video_paths = sorted(glob.glob(os.path.join(data_dir, "*.mp4")))

		media_ids: List[str] = []
		if video_paths:
			media_id = await self.video_uploader.upload_video(video_paths[0])
			media_ids = [media_id]
		else:
			for path in image_paths[:4]:
				media_ids.append(await self.upload_image(path))

		return await self.create_tweet(text=text, media_ids=media_ids or None)

	def _caption_for_media(self, media_path: str, data_dir: str) -> Optional[str]:
		stem = os.path.splitext(os.path.basename(media_path))[0]
		per_file = os.path.join(data_dir, f"{stem}.txt")
		if os.path.isfile(per_file):
			with open(per_file, "r", encoding="utf-8") as f:
				return f.read().strip() or None

		# Fallback to caption.txt, else first .txt in folder
		caption_file = os.path.join(data_dir, "caption.txt")
		if os.path.isfile(caption_file):
			with open(caption_file, "r", encoding="utf-8") as f:
				return f.read().strip() or None

		txt_files = sorted(glob.glob(os.path.join(data_dir, "*.txt")))
		for p in txt_files:
			if os.path.basename(p).lower() != "caption.txt":
				with open(p, "r", encoding="utf-8") as f:
					return f.read().strip() or None
		return None

	def _extract_handle_name(self, node_token) -> tuple[Optional[str], Optional[str]]:
		try:
			if isinstance(node_token, tuple) and len(node_token) >= 2:
				return (node_token[0] or None, node_token[1] or None)
			if isinstance(node_token, dict):
				name = (node_token.get("a") or {}).get("n") or node_token.get("name")
				handle = node_token.get("h") or node_token.get("handle")
				return (handle, name)
			handle = getattr(node_token, "h", None)
			name = getattr(node_token, "name", None)
			return (handle, name)
		except Exception:
			return (None, None)

	async def post_multiple_from_dir(self, data_dir: str = "data", limit: int = 1) -> List[dict]:
		image_patterns = ["*.jpg", "*.jpeg", "*.png", "*.gif"]
		image_paths: List[str] = []
		for p in image_patterns:
			image_paths += glob.glob(os.path.join(data_dir, p))
		image_paths = sorted(image_paths)

		video_paths = sorted(glob.glob(os.path.join(data_dir, "*.mp4")))

		# Build a single media list (post one media per tweet)
		media_queue = video_paths + image_paths

		self.logger.info(
			"Preparing to post from dir: data_dir=%s total_media=%d limit=%d",
			data_dir, len(media_queue), limit,
		)
		responses: List[dict] = []
		for i, path in enumerate(media_queue):
			if i >= max(0, int(limit)):
				break

			text = self._caption_for_media(path, data_dir)
			if path.lower().endswith(".mp4"):
				media_id = await self.video_uploader.upload_video(path)
				resp = await self.create_tweet(text=text, media_ids=[media_id])
			else:
				media_id = await self.upload_image(path)
				resp = await self.create_tweet(text=text, media_ids=[media_id])

			self.logger.info("Posted media %d/%d: %s -> tweet_id=%s", i + 1, limit, path, (resp.get("data") or {}).get("id"))
			responses.append(resp)

		return responses

	async def post_video_from_mega(self, data_dir: str = "data") -> dict:
		"""Download a video from MEGA, tweet it with caption, then delete from MEGA."""
		public_url = os.getenv("MEGA_PUBLIC_URL")
		file_name = os.getenv("MEGA_FILE_NAME")
		# If MEGA_PUBLIC_URL provided, bypass DB uniqueness (we cannot enumerate)
		if public_url:
			local_path, node = self.mega.download_video(dest_dir=data_dir, file_name=None, public_url=public_url)
			chosen_handle, chosen_name = None, None
		else:
			# Choose latest unposted video from the configured MEGA folder
			candidates = self.mega.list_recent_videos()
			chosen = None
			for handle, name, ts in candidates:
				if not self.db.is_mega_posted(handle, name):
					chosen = (handle, name, ts)
					break
			if not chosen:
				raise RuntimeError("No unique MEGA video available to post (all candidates already posted)")
			chosen_handle, chosen_name, _ = chosen
			self.logger.info("Selected MEGA video: handle=%s name=%s", chosen_handle, chosen_name)
			local_path, node = self.mega.download_video(dest_dir=data_dir, file_name=chosen_name, public_url=None)

		text = self._caption_for_media(local_path, data_dir)
		media_id = await self.video_uploader.upload_video(local_path)
		resp = await self.create_tweet(text=text, media_ids=[media_id])
		tweet_id = (resp.get("data") or {}).get("id")

		# Record as posted if we had a concrete MEGA selection
		try:
			if not public_url:
				# Prefer actual handle/name from the downloaded node token
				actual_handle, actual_name = self._extract_handle_name(node)
				self.db.mark_mega_posted(actual_handle or chosen_handle, actual_name or chosen_name, tweet_id)
		except Exception:
			self.logger.warning("Failed to record MEGA post in DB", exc_info=True)

		# If tweet succeeded, try to delete remote file and local copy
		self.mega.delete(node)
		try:
			os.remove(local_path)
		except OSError:
			pass

		self.logger.info("Posted MEGA video and cleaned up: local=%s tweet_id=%s", local_path, (resp.get("data") or {}).get("id"))
		return resp


async def main():
	# Configure logging level and format
	level = (os.getenv("LOG_LEVEL") or "INFO").upper()
	logging.basicConfig(level=getattr(logging, level, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")


	manager = XTweetManager()
	# Read post limit from environment: prefer X_POST_LIMIT, fallback POST_LIMIT
	limit_str = os.getenv("X_POST_LIMIT") or os.getenv("POST_LIMIT") or "1"
	try:
		limit = int(limit_str)
	except ValueError:
		limit = 1
	limit = max(1, limit)

	use_mega = (os.getenv("X_USE_MEGA") or "").lower() in {"1", "true", "yes"}
	if use_mega:
		result = await manager.post_video_from_mega("data")
		print(result)
	else:
		results = await manager.post_multiple_from_dir("data", limit=limit)
		print(results)


# if __name__ == "__main__":
# 	asyncio.run(main())

