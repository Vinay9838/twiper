#!/usr/bin/env bash
set -euo pipefail

# Backup posted.json from the running Fly app into the local repo
APP_NAME="twiper"
REMOTE_PATH="/appsrc/app/storage-manager/db"
LOCAL_DIR="app/storage-manager/db"
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

# Use SFTP session to download the file. It will be saved to the local repo path.
fly ssh sftp -a "$APP_NAME" <<SFTP
cd $REMOTE_PATH
get posted.json $LOCAL_DIR/$BACKUP_FILE
bye
SFTP

# Also update the unversioned posted.json (overwrite) for convenience
cp -f "$LOCAL_DIR/$BACKUP_FILE" "$LOCAL_DIR/posted.json"

echo "Saved: $LOCAL_DIR/$BACKUP_FILE"
echo "Updated: $LOCAL_DIR/posted.json"
