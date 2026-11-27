#!/usr/bin/env bash
# Validate the latest encrypted dump AND restore into a fresh, isolated database.
# NEVER point TEST_RESTORE_DATABASE_URL to the production database.
set -euo pipefail
: "${RESTIC_REPOSITORY:?}"
: "${RESTIC_PASSWORD_FILE:?}"
: "${TEST_RESTORE_DATABASE_URL:?Must be an empty ISOLATED PostgreSQL database in RF}"
case "$TEST_RESTORE_DATABASE_URL" in
  *restore_test*) ;;
  *) echo "ERROR: restore URL must identify an isolated restore_test database" >&2
     exit 2;;
esac
command -v restic >/dev/null || exit 2
command -v pg_restore >/dev/null || exit 2
path="$(restic ls latest --tag leasingcompass-db | awk '/leasingcompass-.*\.dump/ {print $NF}' | tail -1)"
if [ -z "$path" ]; then
  echo "ERROR: no encrypted backup found" >&2
  exit 2
fi
# The operator must create and restrict the disposable restore database
# before this command; pg_restore never gets production credentials here.
restic dump latest "$path" | pg_restore --no-owner --no-acl -d "$TEST_RESTORE_DATABASE_URL"
echo "Restore drill completed. Verify table counts, encrypted fields and data retention policy."
