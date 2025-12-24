# Twiper

Post tweets with text/images/videos from a local data folder or directly from your MEGA account. Includes:

- OAuth1-signed uploads to X (Twitter) v2 `POST /2/tweets`
- Chunked video upload via `upload.twitter.com/1.1/media/upload`
- MEGA integration to download the latest video from a specific folder, then (optionally) delete
- JSON de-duplication so the same MEGA video name is not posted twice
- Structured logging and a clean progress bar for MEGA downloads

## Requirements

- Python 3.10+
- X (Twitter) developer app credentials
- MEGA account (for MEGA flow)

## Environment Variables

Required for OAuth1 to X (Twitter): any of these aliases work.

- X credentials:
  - `X_API_KEY` | `TWITTER_API_KEY` | `CONSUMER_KEY`
  - `X_API_SECRET` | `TWITTER_API_SECRET` | `CONSUMER_SECRET`
  - `X_ACCESS_TOKEN` | `TWITTER_ACCESS_TOKEN`
  - `X_ACCESS_SECRET` | `TWITTER_ACCESS_SECRET`

 Optional:
- `X_USE_MEGA` (true/false)
- `X_POST_LIMIT` (integer)
- `JSON_DB_PATH` (path to local posted.json)
- `LOG_LEVEL` (INFO/DEBUG)
- MEGA: `MEGA_EMAIL`, `MEGA_PASSWORD`, `MEGA_DIR_NAME`, `MEGA_PUBLIC_URL`, `MEGA_HARD_DELETE`, `MEGA_PROGRESS_BAR`

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file at the repo root with your X credentials:

```
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_SECRET=...
```

Optional MEGA credentials and settings:

```
# Enable MEGA posting mode
X_USE_MEGA=true

# MEGA auth (required unless using a public URL)
MEGA_EMAIL=you@example.com
MEGA_PASSWORD=your-password

# Folder to scan (defaults to XYZBlob)
MEGA_DIR_NAME=XYZBlob

# Optional: use a public URL instead of account login
# MEGA_PUBLIC_URL=https://mega.nz/file/XXXXXXXX#YYYYYYYY

# Optional: hard delete instead of moving to trash
# MEGA_HARD_DELETE=true

# Optional: log level and progress bar toggle
LOG_LEVEL=INFO
MEGA_PROGRESS_BAR=1

# Optional: JSON DB location (stores posted filenames)
JSON_DB_PATH=data/posted.json

# Optional: post limit for local data/ flow
# X_POST_LIMIT=3
```

## Deployment (Fly.io + cron)

This app runs a cron inside the container. Cron starts `run_job.sh`, which now sources the environment exported at container start.

- Set secrets in Fly:

```bash
flyctl secrets set \
  X_API_KEY=... \
  X_API_SECRET=... \
  X_ACCESS_TOKEN=... \
  X_ACCESS_SECRET=... \
  MEGA_EMAIL=... MEGA_PASSWORD=...
```

- Optional non-secret env in [env] of `fly.toml` (e.g., `LOG_LEVEL`, `X_POST_LIMIT`).
- The entrypoint writes all env to `/etc/profile.d/container_env.sh` and `run_job.sh` sources it so jobs see secrets.
- If you prefer, you can also define variables directly in `crontab` above the schedule lines (e.g., `X_POST_LIMIT=2`).

Troubleshooting deployed env:
- Exec into the machine and check PID 1 env: `cat /proc/1/environ | tr '\0' '\n'`
- Verify the exported env file: `cat /etc/profile.d/container_env.sh`
- Tail logs: `tail -f /var/log/cron.log`


## How It Works

- Local flow (data/):
  - Reads the first `*.txt` for tweet text (or `caption.txt`),
  - Posts first `*.mp4` (video) or up to 4 images, if present.

- MEGA flow:
  - Scans the `MEGA_DIR_NAME` folder (including subfolders) for videos.
  - Syncs `posted.json` from MEGA, then picks the latest unposted by filename and downloads it.
  - Uploads the video to X as a tweet with a caption sourced from:
    - `data/<basename>.txt`, or `data/caption.txt`, or the first `*.txt` in `data/`.
  - On success, records the filename in `posted.json`, pushes the updated JSON back to the MEGA folder, and deletes only the local downloaded file. Remote MEGA files are left intact.

## Run

- Post from MEGA (recommended):

```bash
. .venv/bin/activate
export X_USE_MEGA=true
python -m app.tweet_manager
```

- Post from local `data/` folder:

```bash
. .venv/bin/activate
export X_USE_MEGA=false
export X_POST_LIMIT=2  # number of tweets to post in one run
python -m app.tweet_manager
```

## Data Folder Conventions

- Place media in `data/`:
  - Videos: `.mp4`
  - Images: `.jpg`, `.jpeg`, `.png`, `.gif`
- Captions:
  - Per-file: `data/<basename>.txt` (e.g., `data/video1.txt`)
  - Global: `data/caption.txt`
  - Fallback: first `*.txt` file in `data/`

`data/.gitkeep` is tracked; everything else in `data/` is ignored by Git (see `.gitignore`).

## De-duplication (JSON)

- File: `data/posted.json` (override via `JSON_DB_PATH`)
- Format: JSON array of filenames (e.g., `["clip1.mp4", "clip2.mp4"]`)
- On start of MEGA flow, the app tries to download `posted.json` from the configured MEGA folder.
- After posting, the filename is appended locally and the JSON is uploaded back to the MEGA folder (replacing any existing remote file).

## Troubleshooting

- MEGA import error on Python 3.12 with tenacity: ensure `tenacity>=8.2.3` (already in `requirements.txt`).
- MEGA files are no longer deleted automatically after posting.
- Public URL mode cannot enumerate MEGA files; de-dup is skipped in that case.
- Enable verbose logs:

```bash
export LOG_LEVEL=DEBUG
```

## Files

- `app/tweet_manager.py` — Orchestrates posting, local and MEGA flows
- `app/media_manager.py` — OAuth1-signed video upload (INIT/APPEND/FINALIZE/STATUS)
- `app/mega_manager.py` — MEGA login/list/download/delete + progress bar
- `app/json_db_manager.py` — JSON tracker for posted MEGA filenames
- `requirements.txt` — Project dependencies
- `.gitignore` — Ignore `data/*` except `data/.gitkeep`, plus common Python artifacts

## Notes

- The X API and media upload endpoints are subject to rate limits and account permissions.
- Ensure your app has permissions for media uploads and tweeting.
