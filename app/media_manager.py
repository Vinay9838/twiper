import aiohttp
import asyncio
import os
import logging
import random
from dotenv import load_dotenv
from oauthlib.oauth1 import Client
from urllib.parse import urlencode

UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
# Use smaller chunk size to reduce peak memory during upload
# Twitter supports chunked upload; smaller chunks mean more requests but lower memory footprint.
CHUNK_SIZE = 1 * 1024 * 1024  # 1MB


class XVideoUploader:
    def __init__(self):
        load_dotenv()
        self.logger = logging.getLogger(__name__)

        self.client = Client(
            client_key=os.getenv("X_API_KEY"),
            client_secret=os.getenv("X_API_SECRET"),
            resource_owner_key=os.getenv("X_ACCESS_TOKEN"),
            resource_owner_secret=os.getenv("X_ACCESS_SECRET"),
            signature_type="AUTH_HEADER",
        )

        if not all([
            os.getenv("X_API_KEY"),
            os.getenv("X_API_SECRET"),
            os.getenv("X_ACCESS_TOKEN"),
            os.getenv("X_ACCESS_SECRET"),
        ]):
            raise RuntimeError("Missing OAuth credentials")
        self.logger.debug("Initialized XVideoUploader with OAuth credentials present")

    def _get_http_timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=600, connect=60, sock_connect=60, sock_read=120)

    # -------- OAuth signing helpers --------

    def sign_form(self, method: str, body: dict) -> dict:
        _, headers, _ = self.client.sign(
            uri=UPLOAD_URL,
            http_method=method,
            body=urlencode(body),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return headers

    def sign_multipart(self, method: str) -> dict:
        _, headers, _ = self.client.sign(
            uri=UPLOAD_URL,
            http_method=method,
        )
        return headers

    def sign_query(self, method: str, params: dict) -> dict:
        query_url = f"{UPLOAD_URL}?{urlencode(params)}"
        _, headers, _ = self.client.sign(
            uri=query_url,
            http_method=method,
        )
        return headers

    # -------- Video upload --------

    async def upload_video(self, path: str) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

        total_bytes = os.path.getsize(path)
        self.logger.info("Starting video upload: path=%s size=%d bytes", path, total_bytes)

        async with aiohttp.ClientSession(timeout=self._get_http_timeout()) as session:
            # ----- INIT -----
            init_body = {
                "command": "INIT",
                "media_type": "video/mp4",
                "total_bytes": total_bytes,
                "media_category": "tweet_video",
            }

            async with session.post(
                UPLOAD_URL,
                data=init_body,
                headers=self.sign_form("POST", init_body),
            ) as r:
                r.raise_for_status()
                media_id = (await r.json())["media_id_string"]
                self.logger.info("INIT complete: media_id=%s", media_id)

            # ----- APPEND -----
            segment_index = 0
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    form = aiohttp.FormData()
                    form.add_field("command", "APPEND")
                    form.add_field("media_id", media_id)
                    form.add_field("segment_index", str(segment_index))
                    # Provide filename and a generic content type to avoid client-side body errors
                    form.add_field(
                        "media",
                        chunk,
                        filename=os.path.basename(path),
                        content_type="application/octet-stream",
                    )

                    append_attempt = 0
                    while True:
                        try:
                            async with session.post(
                                UPLOAD_URL,
                                data=form,
                                headers=self.sign_multipart("POST"),
                            ) as r:
                                r.raise_for_status()
                            break
                        except Exception as e:
                            append_attempt += 1
                            delay = min(5 * (2 ** (append_attempt - 1)), 60) + random.uniform(0, 0.5)
                            self.logger.warning("APPEND retry #%d: media_id=%s segment=%d err=%s; sleeping %.2fs", append_attempt, media_id, segment_index, str(e), delay)
                            await asyncio.sleep(delay)
                    self.logger.debug("APPEND ok: media_id=%s segment=%d bytes=%d", media_id, segment_index, len(chunk) if chunk else 0)
                    segment_index += 1

            # ----- FINALIZE -----
            finalize_body = {
                "command": "FINALIZE",
                "media_id": media_id,
            }

            async with session.post(
                UPLOAD_URL,
                data=finalize_body,
                headers=self.sign_form("POST", finalize_body),
            ) as r:
                r.raise_for_status()
                result = await r.json()
                self.logger.debug("FINALIZE response: %s", result)

            # ----- STATUS -----
            if "processing_info" in result:
                await self.wait_for_processing(session, media_id)

            self.logger.info("Upload succeeded: media_id=%s", media_id)
            return media_id

    async def wait_for_processing(self, session, media_id: str):
        while True:
            params = {
                "command": "STATUS",
                "media_id": media_id,
            }

            async with session.get(
                UPLOAD_URL,
                params=params,
                headers=self.sign_query("GET", params),
            ) as r:
                r.raise_for_status()
                info = (await r.json()).get("processing_info", {})

            state = info.get("state")
            self.logger.debug("Processing state: media_id=%s state=%s info=%s", media_id, state, info)
            if state == "succeeded":
                self.logger.info("Processing succeeded: media_id=%s", media_id)
                return
            if state == "failed":
                raise RuntimeError(f"Processing failed: {info}")

            await asyncio.sleep(info.get("check_after_secs", 5))


# -------- Entry point --------

async def main():
    uploader = XVideoUploader()
    media_id = await uploader.upload_video("data/2.mp4")
    print("Video uploaded successfully. media_id =", media_id)


if __name__ == "__main__":
    asyncio.run(main())
