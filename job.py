import logging
import asyncio
import datetime

from app.tweet_manager import main as tweet_manager_main

logging.basicConfig(level=logging.INFO)

def run_job():
    now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    logging.info("Cron job started at %s", now)

    try:
        asyncio.run(tweet_manager_main())
    except Exception:
        logging.exception("Cron job failed")
        raise

    logging.info("Cron job finished successfully")

if __name__ == "__main__":
    run_job()
