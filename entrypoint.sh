#!/bin/sh
set -e

echo "Entrypoint started"

# Export ALL env vars for cron
printenv | sed 's/^\(.*\)$/export \1/g' > /etc/profile.d/container_env.sh
chmod +x /etc/profile.d/container_env.sh

# Start cron
exec cron -f
