#!/usr/bin/env bash
# Checks a deployed backend from the outside, the way a browser reaches it.
#   deploy/smoke.sh https://yourapp.duckdns.org
set -uo pipefail

BASE="${1:?usage: deploy/smoke.sh https://<your-subdomain>.duckdns.org}"
BASE="${BASE%/}"
# https only: the first check exists to prove the certificate, so a plain-http URL
# would "pass" it without proving anything.
case "$BASE" in https://*) ;; *) echo "Give the https:// address, e.g. https://yourapp.duckdns.org"; exit 2 ;; esac
HOST_ONLY="${BASE#https://}"
fail=0
check() { if [ "$2" = "$3" ]; then echo "  ok    $1"; else echo "  FAIL  $1 (expected $3, got $2)"; fail=1; fi; }

echo "Checking $BASE"
# curl verifies the certificate by default, so a 200 here also proves HTTPS is real.
check "HTTPS with a trusted certificate" "$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/openapi.json")" 200
check "plain http redirects to https"     "$(curl -sS -o /dev/null -w '%{http_code}' "http://$HOST_ONLY/openapi.json")" 308
check "API refuses requests with no token" "$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/me")" 401

headers="$(curl -sS -D - -o /dev/null "$BASE/api/me" | tr -d '\r' | tr 'A-Z' 'a-z')"
for h in "strict-transport-security" "x-content-type-options: nosniff" "x-frame-options: deny" \
         "content-security-policy: default-src 'none'" "cache-control: no-store"; do
  echo "$headers" | grep -q "^$h" && echo "  ok    header $h" || { echo "  FAIL  missing header $h"; fail=1; }
done

[ "$fail" = 0 ] && echo "All checks passed." || echo "Some checks failed."
exit "$fail"
