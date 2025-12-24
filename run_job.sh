#!/bin/sh
set -e

echo "Cron wrapper started at $(date -u)"

# Load container env exported by entrypoint (cron doesn't inherit)
. /etc/profile.d/container_env.sh 2>/dev/null || true

# Ensure working directory is the app root so relative paths (e.g., data/twiper.db) resolve
cd /appsrc || true

# Explicitly export env (cron-safe)
export X_CLIENT_ID
export X_CLIENT_SECRET
export X_ACCESS_TOKEN
export X_REFRESH_TOKEN

exec /usr/local/bin/python3 /appsrc/job.py
