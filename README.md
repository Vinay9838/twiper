# Twiper

Post tweets with text/images/videos from a local data folder or directly from your MEGA account. Includes:

- OAuth1-signed uploads to X (Twitter) v2 `POST /2/tweets`
- Chunked video upload via `upload.twitter.com/1.1/media/upload`
- MEGA integration to download the latest video from a specific folder, then (optionally) delete
- SQLite de-duplication so the same MEGA video is not posted twice
- Structured logging and a clean progress bar for MEGA downloads

## Requirements

- Python 3.10+
- X (Twitter) developer app credentials
- MEGA account (for MEGA flow)

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

# Optional: SQLite DB location
DB_PATH=data/twiper.db

# Optional: post limit for local data/ flow
# X_POST_LIMIT=3
```

## How It Works

- Local flow (data/):
  - Reads the first `*.txt` for tweet text (or `caption.txt`),
  - Posts first `*.mp4` (video) or up to 4 images, if present.

- MEGA flow:
  - Scans the `MEGA_DIR_NAME` folder (including subfolders) for videos.
  - Picks the latest unposted by handle+name (checked in SQLite) and downloads it.
  - Uploads the video to X as a tweet with a caption sourced from:
    - `data/<basename>.txt`, or `data/caption.txt`, or the first `*.txt` in `data/`.
  - On success, records the handle+name in the DB to avoid duplicates, and deletes the file from MEGA (soft or hard) and from `data/`.

## Run

- Post from MEGA (recommended):

```bash
. .venv/bin/activate
export X_USE_MEGA=true
python tweet_manager.py
```

- Post from local `data/` folder:

```bash
. .venv/bin/activate
export X_USE_MEGA=false
export X_POST_LIMIT=2  # number of tweets to post in one run
python tweet_manager.py
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

## De-duplication (SQLite)

- File: `data/twiper.db` (override via `DB_PATH`)
- Table: `posted_media(source, handle, name, tweet_id, posted_at)` with a unique index on `(source, handle, name)`
- MEGA selection uses newest-first order and skips entries already in the DB
- After posting, the actual node handle+name from MEGA is recorded

## Troubleshooting

- MEGA import error on Python 3.12 with tenacity: ensure `tenacity>=8.2.3` (already in `requirements.txt`).
- MEGA delete vs destroy:
  - `delete` moves to trash. Set `MEGA_HARD_DELETE=true` to permanently remove via `destroy`.
- Public URL mode cannot enumerate MEGA files; de-dup is skipped in that case.
- Enable verbose logs:

```bash
export LOG_LEVEL=DEBUG
```

## Files

- `tweet_manager.py` — Orchestrates posting, local and MEGA flows
- `media_manager.py` — OAuth1-signed video upload (INIT/APPEND/FINALIZE/STATUS)
- `mega_manager.py` — MEGA login/list/download/delete + progress bar
- `db_manager.py` — SQLite wrapper for posted-media tracking
- `requirements.txt` — Project dependencies
- `.gitignore` — Ignore `data/*` except `data/.gitkeep`, plus common Python artifacts

## Notes

- The X API and media upload endpoints are subject to rate limits and account permissions.
- Ensure your app has permissions for media uploads and tweeting.
