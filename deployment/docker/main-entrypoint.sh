#!/usr/bin/env bash
set -euo pipefail

assets_path="/home/frappe/frappe-bench/sites/assets"
baked_path="/home/frappe/frappe-bench/assets"

if [[ ! -d "$baked_path" ]]; then
	echo "Baked assets are missing: $baked_path" >&2
	exit 1
fi

rm -rf "$assets_path"
ln -s "$baked_path" "$assets_path"

exec "$@"

