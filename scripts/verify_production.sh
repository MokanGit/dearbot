#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Production Verification Script
# Runs full health, API, WebMCP, and database checks in a single execution.
# ==============================================================================

SERVER_HOST="${SERVER_HOST:-your-server-ip-or-domain}"
SERVER_USER="${SERVER_USER:-root}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_rsa}"
SSH_HOST_KEY_POLICY="${SSH_HOST_KEY_POLICY:-accept-new}"
BASE_URL="${BASE_URL:-https://dearbot.example.com}"
TEST_TOKEN="${TEST_TOKEN:-sample-token-12345}"

echo "============================================================"
echo "🔍 1. Verifying Live Public Endpoints over HTTPS"
echo "============================================================"

# Health check
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health" || echo "000")
echo "• GET /health : HTTP $HTTP_CODE"

# profile.json check
PROFILE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/a/${TEST_TOKEN}/profile.json" || echo "000")
echo "• GET /a/${TEST_TOKEN}/profile.json : HTTP $PROFILE_STATUS"

# Level 1: URL / GET query
GET_RESULT=$(curl -s "$BASE_URL/a/${TEST_TOKEN}/ask?q=Tell+me+about+your+engineering+background" || echo "")
GET_CONF=$(echo "$GET_RESULT" | grep -o '"confidence":\s*"[^"]*"' || echo "none")
echo "• Tier 1 (URL/GET) : $GET_CONF"

# Level 2 / 4: POST / WebMCP query
WEBMCP_RESULT=$(curl -s -X POST "$BASE_URL/a/${TEST_TOKEN}/ask" \
  -H "Content-Type: application/json" \
  -H "X-Access-Method: webmcp" \
  -d '{"question": "Tell me about your engineering background", "access_method": "webmcp", "tool": "ask_cv"}' || echo "")
WEBMCP_CONF=$(echo "$WEBMCP_RESULT" | grep -o '"confidence":\s*"[^"]*"' || echo "none")
echo "• Tier 4 (WebMCP)  : $WEBMCP_CONF"

echo ""
echo "============================================================"
echo "📊 2. Inspecting Remote Docker & Telemetry Database"
echo "============================================================"

ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking="$SSH_HOST_KEY_POLICY" "$SERVER_USER@$SERVER_HOST" <<EOF_REMOTE
echo "• Docker Containers:"
docker ps --filter "name=dearbot-" --format "  - {{.Names}}: {{.Status}}"

echo ""
echo "• Recent Interactions in SQLite (Top 5):"
docker exec dearbot-backend python -c "
import sqlite3
con = sqlite3.connect('/app/backend/data/cv.db')
cur = con.cursor()
rows = cur.execute('''
    SELECT timestamp, access_method, tool, event_type, latency_ms, SUBSTR(question, 1, 40)
    FROM interactions
    ORDER BY timestamp DESC
    LIMIT 5
''').fetchall()
for r in rows:
    print(f'  [{r[0][:19]}] method={r[1]:<7} tool={str(r[2]):<14} latency={str(r[4])}ms event={r[3]} q=\"{r[5]}...\"')
"
EOF_REMOTE

echo ""
echo "============================================================"
echo "✅ All verification checks completed in a single run!"
echo "============================================================"
