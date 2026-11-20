#!/usr/bin/env bash
# Runs ON THE VM (from CI or by hand): update to origin/main, install deps,
# migrate, restart the service, and fail loudly if it doesn't come back healthy.
set -euo pipefail

APP_DIR=/home/azureuser/reveal-be
UV=/home/azureuser/.local/bin/uv

cd "$APP_DIR"
git fetch --quiet origin main
git reset --hard --quiet origin/main
echo "Deploying $(git log --oneline -1)"

"$UV" sync --frozen --no-dev --quiet
.venv/bin/alembic upgrade head

sudo systemctl restart reveal-api

for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8001/health; then
    echo ""
    echo "Healthy."
    exit 0
  fi
  sleep 1
done

echo "Health check failed. Last logs:"
sudo journalctl -u reveal-api -n 60 --no-pager
exit 1
