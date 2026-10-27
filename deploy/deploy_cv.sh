#!/usr/bin/env bash
set -euo pipefail

# 1. Paths and environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_INFRA_PATH="${DEPLOY_INFRA_PATH:-}"

if [[ -n "$DEPLOY_INFRA_PATH" && -f "$DEPLOY_INFRA_PATH/scripts/env.local.sh" ]]; then
  source "$DEPLOY_INFRA_PATH/scripts/env.local.sh"
fi

SERVER_HOST="${SERVER_HOST:-your-server-ip-or-domain}"
SERVER_USER="${SERVER_USER:-root}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_rsa}"
SSH_KEY_PATH="${SSH_KEY_PATH/#\~/$HOME}"
SSH_HOST_KEY_POLICY="${SSH_HOST_KEY_POLICY:-accept-new}"

DEARBOT_BACKEND_IMAGE="dearbot-backend:latest"
DEARBOT_FRONTEND_IMAGE="dearbot-frontend:latest"

REMOTE_APP_DIR="/opt/apps/dearbot"
REMOTE_COMPOSE_FILE="$REMOTE_APP_DIR/docker-compose.yml"
REMOTE_DEPLOY_ENV="$REMOTE_APP_DIR/deploy.env"
REMOTE_RUNTIME_ENV="$REMOTE_APP_DIR/runtime.env"

echo "=== 1. Building Frontend Next.js & Docker Images Locally ==="
echo "Compiling Next.js Standalone Build..."
(cd "$REPO_ROOT/frontend" && npm run build)

echo "Building Backend Docker Image: $DEARBOT_BACKEND_IMAGE..."
docker build -t "$DEARBOT_BACKEND_IMAGE" -f "$REPO_ROOT/backend/Dockerfile" "$REPO_ROOT"

echo "Building Frontend Docker Image: $DEARBOT_FRONTEND_IMAGE..."
docker build -t "$DEARBOT_FRONTEND_IMAGE" -f "$REPO_ROOT/frontend/Dockerfile" "$REPO_ROOT"

echo "=== 2. Setting Up Remote Directories ==="
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$SERVER_USER@$SERVER_HOST" <<EOF_REMOTE
set -euo pipefail
mkdir -p "$REMOTE_APP_DIR"
mkdir -p "$REMOTE_APP_DIR/data/generated_cvs"
mkdir -p "$REMOTE_APP_DIR/data/synced_docs"
mkdir -p "$REMOTE_APP_DIR/data/applications"
mkdir -p "$REMOTE_APP_DIR/data/applications_media"
chown -R 10001:10001 "$REMOTE_APP_DIR/data"
touch "$REMOTE_RUNTIME_ENV"
chmod 600 "$REMOTE_RUNTIME_ENV"
docker network inspect apps-proxy >/dev/null 2>&1 || docker network create apps-proxy
EOF_REMOTE

echo "=== 3. Uploading Docker Compose Configuration ==="
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$REPO_ROOT/deploy/docker-compose.prod.yml" \
  "$SERVER_USER@$SERVER_HOST:$REMOTE_COMPOSE_FILE"

# Upload runtime.env if exists locally, otherwise keep remote
if [[ -f "$REPO_ROOT/deploy/runtime.cv.env" ]]; then
  echo "Syncing local deploy/runtime.cv.env..."
  scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$REPO_ROOT/deploy/runtime.cv.env" \
    "$SERVER_USER@$SERVER_HOST:$REMOTE_RUNTIME_ENV"
  ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$SERVER_USER@$SERVER_HOST" \
    "chmod 600 $REMOTE_RUNTIME_ENV"
fi

echo "=== 4. Streaming Built Images to the Remote Host over SSH ==="
echo "Streaming Backend Image..."
docker save "$DEARBOT_BACKEND_IMAGE" | \
  ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$SERVER_USER@$SERVER_HOST" "docker load"

echo "Streaming Frontend Image..."
docker save "$DEARBOT_FRONTEND_IMAGE" | \
  ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$SERVER_USER@$SERVER_HOST" "docker load"

echo "=== 5. Launching Containers on apps-proxy Network ==="
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$SERVER_USER@$SERVER_HOST" \
  "docker compose -f $REMOTE_COMPOSE_FILE up -d"

echo "=== 6. Updating & Reloading Caddy Ingress ==="
echo "Ensure your reverse proxy / Caddyfile contains the domain block from deploy/Caddyfile.snippet!"
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$SERVER_USER@$SERVER_HOST" \
  "docker exec shared-caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || docker exec caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || true"

echo "=== Deployment Completed Successfully! ==="
echo "Target Host: $SERVER_HOST"

