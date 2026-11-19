#!/usr/bin/env bash
set -euo pipefail
# Restore into a fresh disposable database, never overwrite the active database.
file=${1:?Usage: bash scripts/restore-check.sh PATH.dump}
test -f "$file"
sha256sum -c "$file.sha256"
target="asufc_restore_$(date +%s)_$$"
docker compose exec -T db createdb -U asufc "$target"
trap 'docker compose exec -T db dropdb -U asufc "$target"' EXIT
docker compose exec -T db pg_restore -U asufc -d "$target" --no-owner --no-acl --exit-on-error < "$file"
docker compose exec -T db psql -U asufc -d "$target" -v ON_ERROR_STOP=1 -c "SELECT (SELECT count(*) FROM funding) AS funding_count,(SELECT count(*) FROM purchase) AS purchase_count,(SELECT count(*) FROM audit_event) AS audit_count;"
docker compose exec -T db psql -U asufc -d "$target" -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF EXISTS (SELECT 1 FROM staff_session) THEN RAISE EXCEPTION 'Unexpected sessions in backup'; END IF; END \$\$;"
printf 'Disposable restore succeeded. Active database untouched.\n'
