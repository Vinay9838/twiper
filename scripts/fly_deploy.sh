#!/usr/bin/env bash
set -euo pipefail

# Wrapper deploy script: backup posted.json from Fly, then deploy
APP_NAME="twiper"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

cd "$PROJECT_ROOT"

if ! command -v fly &>/dev/null; then
  echo "fly CLI not found; please install fly (https://fly.io/docs/hands-on/install-flyctl/)" >&2
  exit 1
fi

# Run backup first
echo "Running backup: scripts/fly_backup_posted.sh"
"$SCRIPT_DIR/fly_backup_posted.sh"

# Deploy to Fly
echo "Deploying to Fly (app: $APP_NAME)..."
# Pass any extra args through to fly deploy
fly deploy --app "$APP_NAME" "$@"

echo "Deploy finished."