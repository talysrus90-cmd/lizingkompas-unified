#!/usr/bin/env bash
# Stream PostgreSQL backup directly to encrypted restic storage, no plain dump.
# Run on protected Russian VPS with restic configured for Russian private bucket.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env.production}"
: "${RESTIC_REPOSITORY:?Set Russian restic repository (not a foreign cloud)}"
: "${RESTIC_PASSWORD_FILE:?Set protected restic password file}"
if [ ! -f "$RESTIC_PASSWORD_FILE" ] || [ ! -s "$RESTIC_PASSWORD_FILE" ]; then
  echo "ERROR: missing non-empty restic key file" >&2
  exit 2
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: missing production env file" >&2
  exit 2
fi
command -v restic >/dev/null || { echo "restic is required" >&2; exit 2; }
command -v docker >/dev/null || { echo "docker is required" >&2; exit 2; }
name="leasingcompass-$(date -u +%Y%m%dT%H%M%SZ).dump"
compose=(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.prod.yml")
"${compose[@]}" exec -T db sh -c   'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' |
  restic backup --stdin --stdin-filename "$name" --tag leasingcompass-db
restic check
echo "Encrypted backup completed; independent restore test still required."
