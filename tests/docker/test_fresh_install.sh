#!/bin/bash
# Fresh install test — simulates a new user setting up Apex
# Runs inside a clean Docker container with no prior state
set +e  # Don't exit on errors — we check them manually

PASS=0
FAIL=0
WARN=0

pass() { echo "  PASS  $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }
warn() { echo "  WARN  $1"; WARN=$((WARN+1)); }

echo "========================================"
echo "  Apex Fresh Install Test"
echo "========================================"
echo ""

# -------------------------------------------
# 1. Check repo structure
# -------------------------------------------
echo "[1] Repo structure"

[ -f setup.py ] && pass "setup.py exists" || fail "setup.py missing"
[ -f server/apex.py ] && pass "server/apex.py exists" || fail "server/apex.py missing"
[ -f server/launch.sh ] && pass "server/launch.sh exists" || fail "server/launch.sh (generic) missing"
[ -f server/config.py ] && pass "server/config.py exists" || fail "server/config.py missing"
[ -f server/dashboard.py ] && pass "server/dashboard.py exists" || fail "server/dashboard.py missing"
[ -f server/persona_templates.json ] && pass "persona_templates.json exists" || fail "persona_templates.json missing"
[ -f requirements.txt ] && pass "requirements.txt exists" || fail "requirements.txt missing"
[ -f LICENSE ] && pass "LICENSE exists" || fail "LICENSE missing"
[ -f README.md ] && pass "README.md exists" || fail "README.md missing"
[ -f CONTRIBUTING.md ] && pass "CONTRIBUTING.md exists" || fail "CONTRIBUTING.md missing"
[ -f docs/GETTING_STARTED.md ] && pass "GETTING_STARTED.md exists" || fail "GETTING_STARTED.md missing"
[ -f docs/UPGRADE_GUIDE.md ] && pass "UPGRADE_GUIDE.md exists" || fail "UPGRADE_GUIDE.md missing"
[ -d server/local_model ] && pass "local_model/ bundled" || fail "local_model/ missing"

echo ""

# -------------------------------------------
# 2. Check no Dana-specific content
# -------------------------------------------
echo "[2] No Dana-specific content in server/"

DANA_HITS=$(grep -rn -i 'dana' server/ --include='*.py' --include='*.sh' 2>/dev/null | grep -v '__pycache__\|launch_dana' | wc -l)
if [ "$DANA_HITS" -eq 0 ]; then
    pass "No 'dana' references in server code"
else
    fail "Found $DANA_HITS 'dana' references in server/"
    grep -rn -i 'dana' server/ --include='*.py' --include='*.sh' 2>/dev/null | grep -v '__pycache__\|launch_dana' | head -5
fi

HOMEBREW_HITS=$(grep -rn '/opt/homebrew' server/ setup.py setup/ --include='*.py' --include='*.sh' 2>/dev/null | grep -v '__pycache__' | wc -l)
if [ "$HOMEBREW_HITS" -eq 0 ]; then
    pass "No /opt/homebrew paths in server code"
else
    fail "Found $HOMEBREW_HITS /opt/homebrew references"
    grep -rn '/opt/homebrew' server/ setup.py setup/ --include='*.py' --include='*.sh' 2>/dev/null | grep -v '__pycache__' | head -5
fi

VPN_HITS=$(grep -rn '10\.8\.0\.2' server/ --include='*.py' --include='*.sh' 2>/dev/null | grep -v '__pycache__' | wc -l)
if [ "$VPN_HITS" -eq 0 ]; then
    pass "No hardcoded VPN IPs (10.8.0.2)"
else
    fail "Found $VPN_HITS hardcoded VPN IP references"
fi

SECRET_HITS=$(grep -rn 'a1zWUJkPtoWX\|3b0d4936-ce44' server/ --include='*.py' --include='*.sh' 2>/dev/null | grep -v '__pycache__' | wc -l)
if [ "$SECRET_HITS" -eq 0 ]; then
    pass "No hardcoded secrets (alert token, team ID)"
else
    fail "Found $SECRET_HITS hardcoded secrets!"
fi

# Check launch_dana.sh is NOT in the repo
if [ -f server/launch_dana.sh ]; then
    fail "launch_dana.sh should not be in the repo (gitignored)"
else
    pass "launch_dana.sh not in repo"
fi

echo ""

# -------------------------------------------
# 3. Python imports
# -------------------------------------------
echo "[3] Python imports"

python3 -c "import fastapi; print(f'  fastapi {fastapi.__version__}')" 2>&1 && pass "fastapi imports" || fail "fastapi import failed"
python3 -c "import uvicorn; print(f'  uvicorn {uvicorn.__version__}')" 2>&1 && pass "uvicorn imports" || fail "uvicorn import failed"

# Test local_model import
python3 -c "
import sys, os
sys.path.insert(0, 'server')
os.environ['APEX_WORKSPACE'] = '/tmp'
from local_model.tool_loop import run_tool_loop
print('  local_model.tool_loop OK')
" 2>&1 && pass "local_model imports" || fail "local_model import failed"

# Test apex.py can at least parse (syntax check)
python3 -c "
import ast
with open('server/apex.py') as f:
    ast.parse(f.read())
print('  apex.py parses OK')
" 2>&1 && pass "apex.py syntax valid" || fail "apex.py has syntax errors"

echo ""

# -------------------------------------------
# 4. SSL cert generation (simulates setup Phase 1)
# -------------------------------------------
echo "[4] Certificate generation"

mkdir -p state/ssl
SSL_DIR="state/ssl"

# Generate CA
openssl genrsa -out "$SSL_DIR/ca.key" 2048 2>/dev/null && pass "CA key generated" || fail "CA key generation failed"
openssl req -x509 -new -key "$SSL_DIR/ca.key" -sha256 -days 3650 \
    -out "$SSL_DIR/ca.crt" -subj "/CN=Apex Test CA" 2>/dev/null && pass "CA cert generated" || fail "CA cert generation failed"

# Generate server cert
openssl genrsa -out "$SSL_DIR/apex.key" 2048 2>/dev/null
cat > "$SSL_DIR/ext.cnf" << 'CNFEOF'
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
[req_distinguished_name]
CN = apex-server
[v3_req]
subjectAltName = @alt_names
[alt_names]
IP.1 = 127.0.0.1
DNS.1 = localhost
CNFEOF
openssl req -new -key "$SSL_DIR/apex.key" -out "$SSL_DIR/apex.csr" \
    -subj "/CN=apex-server" -config "$SSL_DIR/ext.cnf" 2>/dev/null
openssl x509 -req -in "$SSL_DIR/apex.csr" -CA "$SSL_DIR/ca.crt" -CAkey "$SSL_DIR/ca.key" \
    -CAcreateserial -out "$SSL_DIR/apex.crt" -days 825 \
    -extfile "$SSL_DIR/ext.cnf" -extensions v3_req 2>/dev/null && pass "Server cert generated" || fail "Server cert generation failed"

# Generate client cert
openssl genrsa -out "$SSL_DIR/client.key" 2048 2>/dev/null
openssl req -new -key "$SSL_DIR/client.key" -out "$SSL_DIR/client.csr" \
    -subj "/CN=apex-client" 2>/dev/null
openssl x509 -req -in "$SSL_DIR/client.csr" -CA "$SSL_DIR/ca.crt" -CAkey "$SSL_DIR/ca.key" \
    -CAcreateserial -out "$SSL_DIR/client.crt" -days 825 2>/dev/null && pass "Client cert generated" || fail "Client cert generation failed"

echo ""

# -------------------------------------------
# 5. Server startup test
# -------------------------------------------
echo "[5] Server startup"

export APEX_SSL_CERT="$SSL_DIR/apex.crt"
export APEX_SSL_KEY="$SSL_DIR/apex.key"
export APEX_SSL_CA="$SSL_DIR/ca.crt"
export APEX_ROOT="$(pwd)"
export APEX_WORKSPACE="/tmp"
export APEX_PORT=8300
export APEX_MODEL="claude-sonnet-4-6"

# Start server in background
cd "$(pwd)"
python3 server/apex.py &
SERVER_PID=$!
sleep 4

# Check if still running
if kill -0 $SERVER_PID 2>/dev/null; then
    pass "Server started (PID $SERVER_PID)"
else
    fail "Server crashed on startup"
    # Show any error output
    wait $SERVER_PID 2>/dev/null || true
fi

# Test health endpoint (using client cert for mTLS)
HEALTH_CODE=$(curl -sk --cert "$SSL_DIR/client.crt" --key "$SSL_DIR/client.key" \
    --cacert "$SSL_DIR/ca.crt" \
    https://localhost:8300/health -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")

if [ "$HEALTH_CODE" = "200" ]; then
    pass "Health endpoint returns 200"
else
    fail "Health endpoint returned $HEALTH_CODE"
fi

# Test main page
PAGE_CODE=$(curl -sk --cert "$SSL_DIR/client.crt" --key "$SSL_DIR/client.key" \
    --cacert "$SSL_DIR/ca.crt" \
    https://localhost:8300/ -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")

if [ "$PAGE_CODE" = "200" ]; then
    pass "Main page returns 200"
else
    fail "Main page returned $PAGE_CODE"
fi

# Test dashboard
DASH_CODE=$(curl -sk --cert "$SSL_DIR/client.crt" --key "$SSL_DIR/client.key" \
    --cacert "$SSL_DIR/ca.crt" \
    https://localhost:8300/admin/ -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")

if [ "$DASH_CODE" = "200" ]; then
    pass "Dashboard returns 200"
else
    fail "Dashboard returned $DASH_CODE"
fi

# Test persona templates endpoint
TEMPLATES=$(curl -sk --cert "$SSL_DIR/client.crt" --key "$SSL_DIR/client.key" \
    --cacert "$SSL_DIR/ca.crt" \
    https://localhost:8300/api/persona-templates 2>/dev/null)

TEMPLATE_COUNT=$(echo "$TEMPLATES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [ "$TEMPLATE_COUNT" -gt 0 ]; then
    pass "Persona templates endpoint returns $TEMPLATE_COUNT templates"
else
    fail "Persona templates endpoint returned no templates"
fi

# Test features endpoint
FEATURES=$(curl -sk --cert "$SSL_DIR/client.crt" --key "$SSL_DIR/client.key" \
    --cacert "$SSL_DIR/ca.crt" \
    https://localhost:8300/api/features 2>/dev/null)
echo "  Features: $FEATURES"

# Check DB was created with tables
if [ -f state/apex.db ]; then
    pass "Database created"
    TABLE_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('state/apex.db')
tables = conn.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table'\").fetchone()[0]
print(tables)
conn.close()
" 2>/dev/null || echo "0")
    if [ "$TABLE_COUNT" -gt 3 ]; then
        pass "Database has $TABLE_COUNT tables"
    else
        fail "Database only has $TABLE_COUNT tables (expected >3)"
    fi
else
    fail "Database not created"
fi

# Kill server
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null || true

echo ""

# -------------------------------------------
# Summary
# -------------------------------------------
echo "========================================"
echo "  Results: $PASS passed, $FAIL failed, $WARN warnings"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
