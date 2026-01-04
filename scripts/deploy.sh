#!/usr/bin/env bash
set -euo pipefail

# Deploy wrapper: run backup then deploy to Fly
APP_NAME="twiper"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v fly &>/dev/null; then
  echo "fly CLI not found; please install fly (https://fly.io/docs/hands-on/install-flyctl/)" >&2
  exit 1
fi

echo "Running backup: $SCRIPT_DIR/backup.sh"
"$SCRIPT_DIR/backup.sh"

echo "Deploying to Fly (app: $APP_NAME)..."
# Pass through any extra args to fly deploy
fly deploy --app "$APP_NAME" "$@"

echo "Deploy finished."