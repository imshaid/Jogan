#!/usr/bin/env bash
# Apply the Supabase migrations to a throwaway Postgres 17 container and run the row-level
# security and audit checks in tests/db/ (make test-db; CI runs it too). Needs Docker.
set -euo pipefail
cd "$(dirname "$0")/.."

name="jogan-test-db-$$"
docker run -d --rm --name "$name" -e POSTGRES_PASSWORD=test postgres:17-alpine >/dev/null
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT

# TCP only: the image's first, init-time server listens on the socket alone
until docker exec "$name" pg_isready -h 127.0.0.1 -U postgres -q; do sleep 0.5; done
run() { docker exec -i "$name" psql -h 127.0.0.1 -U postgres -v ON_ERROR_STOP=1 -q -o /dev/null; }

run <tests/db/auth_stub.sql
for f in supabase/migrations/*.sql; do
  echo "migration $(basename "$f")"
  run <"$f"
done
run <tests/db/rls.sql
