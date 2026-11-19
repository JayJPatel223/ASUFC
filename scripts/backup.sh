#!/usr/bin/env bash
set -euo pipefail
umask 077
# Run from repository root on authorized host. Never commit the archive.
dir=${1:-backups}
mkdir -p "$dir"
file="$dir/asufc-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
tmp=$(mktemp "$dir/.asufc-XXXXXX")
trap 'rm -f "$tmp"' EXIT
docker compose exec -T db pg_dump -U asufc -d asufc -Fc --no-owner --no-acl --exclude-table-data=public.staff_session --exclude-table-data=public.staff_login_attempt > "$tmp"
docker compose exec -T db pg_restore --list < "$tmp" >/dev/null
mv "$tmp" "$file"
sha256sum "$file" > "$file.sha256"
printf 'Backup created: %s\n' "$file"
