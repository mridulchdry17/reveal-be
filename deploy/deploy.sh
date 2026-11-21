#!/usr/bin/env bash
# Runs ON THE VM: update a checkout to its branch, install deps, migrate,
# restart its service, and fail loudly if it doesn't come back healthy.
#
#   bash deploy.sh production   # ~/reveal-be          main         reveal-api          :8001
#   bash deploy.sh staging      # ~/reveal-be-staging  pre-release  reveal-api-staging  :8002
set -euo pipefail

TARGET="${1:-production}"
case "$TARGET" in
  production) APP_DIR=/home/azureuser/reveal-be;         BRANCH=main;        SERVICE=reveal-api;         PORT=8001 ;;
  staging)    APP_DIR=/home/azureuser/reveal-be-staging; BRANCH=pre-release; SERVICE=reveal-api-staging; PORT=8002 ;;
  *) echo "Usage: deploy.sh [production|staging]"; exit 1 ;;
esac
UV=/home/azureuser/.local/bin/uv

cd "$APP_DIR"
git fetch --quiet origin "$BRANCH"
git checkout --quiet --force -B "$BRANCH" "origin/$BRANCH"
echo "Deploying $TARGET: $(git log --oneline -1)"

"$UV" sync --frozen --no-dev --quiet
.venv/bin/alembic upgrade head

sudo systemctl restart "$SERVICE"

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$PORT/health"; then
    echo ""
    echo "Healthy."
    exit 0
  fi
  sleep 1
done

echo "Health check failed. Last logs:"
sudo journalctl -u "$SERVICE" -n 60 --no-pager
exit 1
