#!/usr/bin/env bash
# Run only on the approved Russian backup/restore host. Never restore to a live DB.
# The temporary PostgreSQL cluster has no network, host mounts, or persistent data.
set -euo pipefail
: "${RESTIC_REPOSITORY:?Set approved Russian restic repository}"
: "${RESTIC_PASSWORD_FILE:?Set protected restic password file}"
if [[ -n "${TEST_RESTORE_DATABASE_URL:-}" ]]; then
  echo "ERROR: external restore URLs are no longer accepted" >&2
  exit 2
fi
[[ -s "$RESTIC_PASSWORD_FILE" ]] || exit 2
for cmd in restic docker python3; do command -v "$cmd" >/dev/null || exit 2; done
# Pin a single tagged snapshot, never resolve 'latest' twice.
snapshot="$(restic snapshots --tag leasingcompass-db --json | python3 -c '
import json, re, sys
items = json.load(sys.stdin)
if not items: sys.exit("No tagged database snapshot")
item = max(items, key=lambda x: x["time"])
sid = item["id"]
if not re.fullmatch(r"[a-f0-9]{64}", sid): sys.exit("Invalid snapshot id")
print(sid)
')"
dump_path="$(restic ls --json "$snapshot" | python3 -c '
import json, re, sys
paths = []
for line in sys.stdin:
    item = json.loads(line)
    path = item.get("path", "")
    if item.get("type") == "file" and re.fullmatch(r"/leasingcompass-[0-9]{8}T[0-9]{6}Z[.]dump", path):
        paths.append(path)
if len(paths) != 1: sys.exit("Expected exactly one database dump")
print(paths[0])
')"
# The same PostgreSQL major version as production. No implicit image download.
# tmpfs is intentionally bounded; larger deployments need an approved isolated host.
size="${COMPASS_RESTORE_TMPFS_SIZE:-2g}"
[[ "$size" =~ ^[1-9][0-9]*[mMgG]$ ]] || exit 2
container="compass-restore-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
cid=""
cleanup() {
  if [[ -n "$cid" ]]; then docker rm -f "$cid" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cid="$(docker run -d --rm --pull=never --name "$container" --network none \
  --security-opt no-new-privileges:true \
  --tmpfs "/var/lib/postgresql/data:rw,nosuid,nodev,size=$size" \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=compass_restore \
  postgres:16-bookworm -c listen_addresses='')"
ready=0
for _ in $(seq 1 60); do
  # Wait for final postgres (PID 1), not the entrypoint's temporary init server.
  if docker exec "$cid" sh -c 'test "$(cat /proc/1/comm)" = postgres && pg_isready -q -U postgres -d compass_restore'; then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" == 1 ]] || { echo "ERROR: isolated database did not start" >&2; exit 2; }
# Hide detailed restore errors, which could otherwise include customer values.
if ! restic dump "$snapshot" "$dump_path" | docker exec -i "$cid" \
  pg_restore --exit-on-error --single-transaction --no-owner --no-acl \
  -U postgres -d compass_restore >/dev/null 2>&1; then
  echo "ERROR: isolated database restore failed" >&2
  exit 2
fi
# Check actual schema and ciphertext markers without exposing any row values.
if ! docker exec -i "$cid" psql -X -q -v ON_ERROR_STOP=1 -U postgres -d compass_restore >/dev/null 2>&1 <<'SQL'
DO $$
BEGIN
  PERFORM count(*) FROM django_migrations;
  PERFORM count(*) FROM intake_quote;
  PERFORM count(*) FROM intake_auditevent;
  PERFORM count(*) FROM auth_user;
  -- Internal financial cases must have no customer contacts at all.
  -- Public/application cases must still carry encrypted required contacts.
  IF EXISTS (SELECT 1 FROM intake_lead WHERE
    (source = 'broker_internal' AND (
      client_name IS DISTINCT FROM '' OR phone IS DISTINCT FROM '' OR
      email IS DISTINCT FROM '' OR company IS DISTINCT FROM '' OR
      inn IS DISTINCT FROM '' OR message IS DISTINCT FROM '' OR
      consent_version IS DISTINCT FROM '' OR consent_text_sha256 IS DISTINCT FROM '' OR
      source_ip_digest IS DISTINCT FROM ''))
    OR (source IS DISTINCT FROM 'broker_internal' AND (
      client_name NOT LIKE 'enc:v1:%' OR phone NOT LIKE 'enc:v1:%' OR
      (email <> '' AND email NOT LIKE 'enc:v1:%') OR
      (company <> '' AND company NOT LIKE 'enc:v1:%') OR
      (inn <> '' AND inn NOT LIKE 'enc:v1:%') OR
      (message <> '' AND message NOT LIKE 'enc:v1:%')))) OR
    EXISTS (SELECT 1 FROM intake_callbackrequest WHERE phone NOT LIKE 'enc:v1:%'
      OR (name <> '' AND name NOT LIKE 'enc:v1:%')) THEN
    RAISE EXCEPTION 'Unexpected plaintext';
  END IF;
END $$;
SQL
then
  echo "ERROR: restored schema or ciphertext marker verification failed" >&2
  exit 2
fi
# Explicitly remove container before reporting success; trap retries on failure.
docker rm -f "$cid" >/dev/null
cid=""
echo "Isolated restore passed: schema and ciphertext markers checked; temporary database removed."
echo "Separate key recovery/decryption, data reconciliation and operator approval still required."
