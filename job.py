import logging
import asyncio
import datetime
import time
import random

from app.tweet_manager import main as tweet_manager_main

logging.basicConfig(level=logging.INFO)

def run_job():
    now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    logging.info("Cron job started at %s", now)

    last_exc = None
    for attempt in range(1, 6):
        try:
            asyncio.run(tweet_manager_main())
            logging.info("Cron job finished successfully")
            return
        except Exception as exc:
            last_exc = exc
            logging.warning(
                "Cron job attempt %d/5 failed: %s",
                attempt,
                exc.__class__.__name__,
                exc_info=True,
            )
            if attempt < 5:
                delay = min(5 * (2 ** (attempt - 1)), 60) + random.uniform(0, 0.5)
                logging.info("Retrying in %.2fs (attempt=%d)", delay, attempt + 1)
                time.sleep(delay)
                continue
            else:
                logging.exception("Cron job failed after 5 attempts")
                raise last_exc

if __name__ == "__main__":
    run_job()
