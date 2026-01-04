#!/usr/bin/env bash
set -euo pipefail

# Backup posted.json from the running Fly app into the local repo using project root
APP_NAME="twiper"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REMOTE_PATH="/appsrc/app/storage-manager/db"
LOCAL_DIR="$ROOT_DIR/app/storage-manager/db"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
BACKUP_FILE="posted.json.${TIMESTAMP}"

mkdir -p "$LOCAL_DIR"

if ! command -v fly &>/dev/null; then
  echo "fly CLI not found; please install fly (https://fly.io/docs/hands-on/install-flyctl/)" >&2
  exit 1
fi

# Ensure user is logged in
if ! fly auth whoami >/dev/null 2>&1; then
  echo "You are not logged in to Fly. Run: fly auth login"
  exit 1
fi

echo "Fetching posted.json from app '$APP_NAME'..."

# If there's an existing posted.json, archive it with a timestamped suffix
if [ -f "$LOCAL_DIR/posted.json" ]; then
  mv "$LOCAL_DIR/posted.json" "$LOCAL_DIR/posted.json.$TIMESTAMP"
  echo "Archived existing posted.json -> $LOCAL_DIR/posted.json.$TIMESTAMP"
fi

# Download posted.json directly into the canonical filename (no timestamp)
fly ssh sftp --app "$APP_NAME" get "$REMOTE_PATH/posted.json" "$LOCAL_DIR/posted.json"

# Basic sanity check: ensure the downloaded file is non-empty
if [ ! -s "$LOCAL_DIR/posted.json" ]; then
  echo "Error: downloaded posted.json is empty or missing" >&2
  exit 2
fi

echo "Saved: $LOCAL_DIR/posted.json"
