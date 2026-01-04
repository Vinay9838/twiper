# Twiper

Post tweets with text/images/videos from a local data folder or directly from your Google Drive folder (service account). Includes:

- OAuth1-signed uploads to X (Twitter) v2 `POST /2/tweets`
- Chunked video upload via `upload.twitter.com/1.1/media/upload`
- Google Drive integration to download the latest video from a specific folder
- Local JSON de-duplication so the same video name is not posted twice
- Structured logging for downloads and posting

## Requirements

- Python 3.10+
- X (Twitter) developer app credentials
- Google Cloud service account with Drive API enabled (for Drive flow)

## Environment Variables

Required for OAuth1 to X (Twitter): any of these aliases work.

- X credentials:
  - `X_API_KEY` | `TWITTER_API_KEY` | `CONSUMER_KEY`
  - `X_API_SECRET` | `TWITTER_API_SECRET` | `CONSUMER_SECRET`
  - `X_ACCESS_TOKEN` | `TWITTER_ACCESS_TOKEN`
  - `X_ACCESS_SECRET` | `TWITTER_ACCESS_SECRET`

 Optional:
- `X_USE_GDRIVE` (true/false)
- `X_POST_LIMIT` (integer)
- `LOG_LEVEL` (INFO/DEBUG)
- Google Drive: `GDRIVE_SERVICE_ACCOUNT_FILE` or `GDRIVE_SERVICE_ACCOUNT_JSON`, `GDRIVE_DIR_NAME`, `GDRIVE_FOLDER_ID`, `GDRIVE_DRIVE_ID`

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

Notes on the local JSON DB:

```
# Local de-dup DB path (fixed)
# File is stored at app/storage-manager/db/posted.json
```

Optional Google Drive settings (service account):

```
# Enable Google Drive posting mode
X_USE_GDRIVE=true

# Service account credentials (one of):
GDRIVE_SERVICE_ACCOUNT_FILE=/path/to/key.json
# or inline JSON (not recommended for production):
# GDRIVE_SERVICE_ACCOUNT_JSON={"type":"service_account", ...}

# Folder to scan (default XYZBlob). Use ID for faster lookup.
GDRIVE_DIR_NAME=XYZBlob
# If known, set explicit folder ID to avoid name search
# GDRIVE_FOLDER_ID=1AbCdEfGhIjKlMnOp

# Shared drive support (optional). If your folder lives in a shared drive,
# set the drive ID to enable AllDrives operations.
# GDRIVE_DRIVE_ID=0AHAbCdEfGhIjKlMnP
```

## Deployment (Fly.io + cron)

This app runs a cron inside the container. Cron starts `run_job.sh`, which sources the environment exported at container start.

- Set secrets in Fly:

```bash
flyctl secrets set \
  X_API_KEY=... \
  X_API_SECRET=... \
  X_ACCESS_TOKEN=... \
  X_ACCESS_SECRET=... \
  GDRIVE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ... }' \
  GDRIVE_FOLDER_ID=... \
  X_USE_GDRIVE=true
```

### Deployment helper (Makefile) ✅

There is a `Makefile` with a `deploy` target that runs a backup of `posted.json` from the running Fly app before calling `fly deploy`.

Usage:

```bash
# Backup only
make backup

# Backup then deploy (forward extra flags to fly deploy after --)
make deploy -- --remote-only
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

- Google Drive flow:
  - Scans the configured Drive folder (including subfolders) for videos.
  - Picks the latest unposted by filename (using local JSON de-dup) and downloads it.
  - Uploads the video to X as a tweet with a caption sourced from:
    - `data/<basename>.txt`, or `data/caption.txt`, or the first `*.txt` in `data/`.
  - Records the filename in the local `posted.json` on success, and always deletes the local downloaded file after the attempt (success or failure).
  - Drive files are not deleted or modified.

## Run

- Post from local `data/` folder:

```bash
. .venv/bin/activate
export X_USE_GDRIVE=false
export X_POST_LIMIT=2  # number of tweets to post in one run
python -m app.tweet_manager
```

- Post from Google Drive:

```bash
. .venv/bin/activate
export X_USE_GDRIVE=true
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

- File: `app/storage-manager/db/posted.json` (fixed location)
- Format: JSON array of filenames (e.g., `["clip1.mp4", "clip2.mp4"]`)
- The file is kept locally only; it is not synced to Google Drive.

## Troubleshooting

- For Google Drive, ensure the service account has access to the target folder (Shared Drive recommended for team setups). If using a personal My Drive, share the folder with the service account email.
- Enable verbose logs:

```bash
export LOG_LEVEL=DEBUG
```

## Files

- `app/tweet_manager.py` — Orchestrates posting, local and Google Drive flows
- `app/media_manager.py` — OAuth1-signed video upload (INIT/APPEND/FINALIZE/STATUS)
- `app/mega_manager.py` — MEGA manager (present but not used by default)
- `app/storage-manager/gdrive/gdrive_manager.py` — Google Drive list/upload/download/delete (service account)
- `app/json_db_manager.py` — JSON tracker for posted filenames
- `requirements.txt` — Project dependencies
- `.gitignore` — Ignore `data/*` except `data/.gitkeep`, plus common Python artifacts

## Notes

- The X API and media upload endpoints are subject to rate limits and account permissions.
- Ensure your app has permissions for media uploads and tweeting.
