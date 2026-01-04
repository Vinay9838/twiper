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

# Download into a temporary file, validate it, then atomically move into place
TMP_FILE="$LOCAL_DIR/posted.json.tmp.$TIMESTAMP.$$"
# Ensure temporary file is removed on exit if something goes wrong
trap 'rm -f "$TMP_FILE"' EXIT

fly ssh sftp --app "$APP_NAME" get "$REMOTE_PATH/posted.json" "$TMP_FILE"

# Basic sanity check: ensure the downloaded file is non-empty
if [ ! -s "$TMP_FILE" ]; then
  echo "Error: downloaded posted.json is empty or missing" >&2
  exit 2
fi

# Atomically replace the canonical file
mv "$TMP_FILE" "$LOCAL_DIR/posted.json"
# Explicitly remove the temporary file path if it still exists (defensive)
if [ -e "$TMP_FILE" ]; then
  rm -f "$TMP_FILE"
fi
# Cancel the trap since file has been moved/cleaned successfully
trap - EXIT

echo "Saved: $LOCAL_DIR/posted.json"
