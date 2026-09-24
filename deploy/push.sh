#!/usr/bin/env bash
# Ship the COMMITTED backend to the server, install the locked dependencies, run
# migrations, and restart. Run from your laptop, every time you deploy.
#
#   deploy/push.sh ubuntu@<server-ip>
#
# Uses git archive, so the server runs exactly what is committed: uncommitted edits
# never ride along by accident, and the server needs no GitHub credentials.
# The previous release is kept as backend.prev; if a push goes wrong, on the server:
#   sudo mv /opt/fantasai/backend /opt/fantasai/backend.bad \
#     && sudo mv /opt/fantasai/backend.prev /opt/fantasai/backend \
#     && sudo systemctl restart fantasai
set -euo pipefail

HOST="${1:?usage: deploy/push.sh ubuntu@<server-ip>}"
cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain -- backend)" ]; then
  echo "backend/ has uncommitted changes. Commit them first, so the server runs what you tested."
  exit 1
fi
REV="$(git rev-parse --short HEAD)"
echo "==> Shipping backend at $REV to $HOST"

ssh "$HOST" "sudo rm -rf /opt/fantasai/backend.new && sudo mkdir -p /opt/fantasai/backend.new"
git archive --format=tar HEAD backend | ssh "$HOST" "sudo tar -x -C /opt/fantasai/backend.new --strip-components=1"

ssh "$HOST" "sudo REV=$REV bash -s" <<'REMOTE'
set -euo pipefail
APP=/opt/fantasai
cd "$APP"
grep -q "^ESPN_COOKIE_KEY=." .env || { echo "ESPN_COOKIE_KEY is empty in $APP/.env; fill it in first."; exit 1; }
grep -q "^CLERK_SECRET_KEY=." .env || { echo "CLERK_SECRET_KEY is empty in $APP/.env; without it auth is OFF."; exit 1; }
echo "$REV" > backend.new/REVISION
chown -R fantasai:fantasai backend.new

echo "==> Dependencies (exact lock, extras removed)"
sudo -u fantasai env UV_CACHE_DIR="$APP/.cache/uv" \
  uv pip sync --python "$APP/venv/bin/python" backend.new/requirements.lock

echo "==> Migrations (before the swap: if one fails, the old release keeps serving)"
(cd backend.new && sudo -u fantasai "$APP/venv/bin/alembic" upgrade head)

echo "==> Swap and restart"
rm -rf backend.prev
[ -d backend ] && mv backend backend.prev
mv backend.new backend
systemctl restart fantasai

for i in $(seq 1 30); do
  curl -fsS -o /dev/null http://127.0.0.1:8000/openapi.json 2>/dev/null && break
  sleep 1
done
curl -fsS -o /dev/null http://127.0.0.1:8000/openapi.json \
  && echo "Backend $REV is up." \
  || { echo "Backend did not come up. Logs: sudo journalctl -u fantasai -n 80"; exit 1; }
REMOTE

echo "Done. Check it from outside with: deploy/smoke.sh https://<your-subdomain>.duckdns.org"
