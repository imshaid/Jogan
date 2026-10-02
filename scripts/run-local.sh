#!/usr/bin/env bash
# Run Jogan on this machine without any account (make run): the API on :8000 with the in-memory
# store, and the web app on :3000 with local sign-in as analyst or approver. Builds the deployed
# demo world (full, seed 42) into bundle/ if there is none yet. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

UV=${UV:-uv}
API_PORT=${API_PORT:-8000}
WEB_PORT=${WEB_PORT:-3000}

if [[ ! -f bundle/meta.json ]]; then
  echo "No bundle/ yet: building the deployed demo world (full, seed 42; about 80 s, once)."
  "$UV" run python -m jogan.api.bundle --profile full --seed 42 --out bundle
fi
if [[ ! -d web/node_modules ]]; then
  echo "Installing the web app's dependencies (npm ci)."
  (cd web && npm ci --no-audit --no-fund)
fi

JOGAN_STORE=memory JOGAN_ENV=development JOGAN_BUNDLE_DIR=bundle JOGAN_TRUSTED_PROXY_HOPS=0 \
  JOGAN_CORS_ORIGINS="http://localhost:$WEB_PORT" \
  "$UV" run uvicorn --factory jogan.api.app:from_env --port "$API_PORT" &
api=$!
trap 'kill "$api" 2>/dev/null || true' EXIT INT TERM

until curl -sf "http://localhost:$API_PORT/health" >/dev/null; do
  kill -0 "$api" 2>/dev/null || { echo "The API did not start (see above)." >&2; exit 1; }
  sleep 0.5
done

cat <<EOF

  API  http://localhost:$API_PORT  (docs at /docs; bearer tokens "analyst" and "approver")
  Web  http://localhost:$WEB_PORT  (sign in under "Local run" as analyst or approver)

  Decisions live in memory until you stop. Ctrl+C stops both.

EOF
cd web
NEXT_PUBLIC_API_BASE_URL="http://localhost:$API_PORT" NEXT_PUBLIC_LOCAL_AUTH=1 npm run dev -- --port "$WEB_PORT"
