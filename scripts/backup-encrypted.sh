#!/usr/bin/env bash
set -euo pipefail
umask 077
# age public recipient only. Keep the private identity offline and separate.
dir=${1:?Specify approved private backup directory}
recipient=${ASUFC_BACKUP_RECIPIENT:?Set age public recipient}
mkdir -p "$dir"
file="$dir/asufc-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump.age"
tmp=$(mktemp "$dir/.asufc-XXXXXX")
trap 'rm -f "$tmp"' EXIT
docker compose exec -T db pg_dump -U asufc -d asufc -Fc --no-owner --no-acl --exclude-table-data=public.staff_session --exclude-table-data=public.staff_login_attempt | age -r "$recipient" -o "$tmp"
test -s "$tmp"
mv "$tmp" "$file"
sha256sum "$file" > "$file.sha256"
printf 'Encrypted backup created: %s\n' "$file"
