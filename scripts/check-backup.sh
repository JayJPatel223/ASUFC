#!/usr/bin/env bash
set -euo pipefail
dir=${1:?Specify backup directory}
hours=${2:-30}
[[ "$hours" =~ ^[1-9][0-9]*$ ]] || exit 2
latest=$(find "$dir" -maxdepth 1 -type f -name '*.dump.age' -printf '%T@ %p\n' | sort -nr | head -n1 || true)
[[ -n "$latest" ]] || { echo "ERROR: no encrypted backup" >&2; exit 1; }
file=${latest#* }
[[ -s "$file" && -f "$file.sha256" ]] || { echo "ERROR: incomplete backup" >&2; exit 1; }
[[ $(find "$file" -mmin "-$((hours*60))" -print) ]] || { echo "ERROR: stale backup" >&2; exit 1; }
sha256sum -c "$file.sha256"
echo "Backup freshness and checksum verified"
