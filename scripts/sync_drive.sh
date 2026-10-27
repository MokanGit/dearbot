#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Google Drive Knowledge Sync Script
#
# Usage:
#   ./scripts/sync_drive.sh              # Syncs from Drive, updates local DB, and deploys to remote server
#   ./scripts/sync_drive.sh --local-only # Syncs from Drive and updates local DB only
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SERVER_HOST="${SERVER_HOST:-your-server-ip-or-domain}"
SERVER_USER="${SERVER_USER:-root}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_rsa}"
SSH_HOST_KEY_POLICY="${SSH_HOST_KEY_POLICY:-accept-new}"

LOCAL_ONLY=false
if [[ "${1:-}" == "--local-only" ]]; then
  LOCAL_ONLY=true
fi

echo "============================================================"
echo "🚀 1. Fetching Latest Master Documents from Google Drive"
echo "============================================================"

# Run local ingestion and DB update
PYTHONPATH="$REPO_ROOT" "$REPO_ROOT/backend/venv/bin/python" "$REPO_ROOT/backend/app/scripts/sync_knowledge.py"

if [[ "$LOCAL_ONLY" == true ]]; then
  echo ""
  echo "ℹ️  --local-only flag set. Skipping production deployment."
  exit 0
fi

echo ""
echo "============================================================"
echo "🌐 2. Syncing Documents to the Remote Production Host"
echo "============================================================"

# Ensure remote directories exist
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$SERVER_USER@$SERVER_HOST" \
  "mkdir -p /opt/apps/dearbot/data/synced_docs"

# Sync markdown files to remote host
echo "• Copying markdown files to the remote host..."
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" -r \
  "$REPO_ROOT/backend/data/synced_docs/"* \
  "$SERVER_USER@$SERVER_HOST:/opt/apps/dearbot/data/synced_docs/"

# Sync service account if present
if [[ -f "$REPO_ROOT/backend/service_account.json" ]]; then
  echo "• Syncing service_account.json to remote data volume..."
  scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" \
    "$REPO_ROOT/backend/service_account.json" \
    "$SERVER_USER@$SERVER_HOST:/opt/apps/dearbot/data/service_account.json"
fi

# Run sync in remote container
echo "• Updating production SQLite database in container..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$SERVER_USER@$SERVER_HOST" <<'EOF_REMOTE'
docker exec dearbot-backend python -c "
import asyncio
from backend.app.database import AsyncSessionLocal
from backend.app.services.google_drive import GoogleDriveService

async def sync():
    async with AsyncSessionLocal() as session:
        g = GoogleDriveService()
        res = await g.sync_documents(session)
        print(f'✓ Remote DB updated: {res[\"total_documents\"]} total documents (added: {res[\"added\"]}, updated: {res[\"updated\"]}, unchanged: {res[\"unchanged\"]})')

asyncio.run(sync())
"
EOF_REMOTE

echo ""
echo "============================================================"
echo "✅ Master documents successfully synced to production!"
echo "Target Host: $SERVER_HOST"
echo "============================================================"
