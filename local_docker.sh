#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

echo "=== 1. Building Frontend Next.js Standalone Build Locally ==="
if command -v pnpm >/dev/null 2>&1; then
  (cd "$REPO_ROOT/frontend" && pnpm run build)
else
  (cd "$REPO_ROOT/frontend" && npm run build)
fi

echo "=== 2. Building and Starting Local Docker Containers ==="
(cd "$REPO_ROOT" && docker compose build && docker compose up -d)

echo "=== 3. Local Containers Running ==="
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000"
echo "To view logs: docker compose logs -f"
echo "To stop:      docker compose down"

