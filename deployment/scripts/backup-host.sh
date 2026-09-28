#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
deployment_dir=$(cd -- "${script_dir}/.." && pwd)
env_file="${deployment_dir}/.env"

if [[ ! -f "$env_file" ]]; then
	echo "Missing deployment environment file: ${env_file}" >&2
	exit 1
fi

set -a
# The file is root-controlled deployment configuration and is intentionally sourced.
# shellcheck disable=SC1090
source "$env_file"
set +a

backup_dir=${BACKUP_DIR:-/var/backups/rmu-lms}
if [[ "$backup_dir" != /var/backups/rmu-lms ]]; then
	echo "BACKUP_DIR must be /var/backups/rmu-lms." >&2
	exit 1
fi

if [[ ! -d "$backup_dir/restic" || ! -w "$backup_dir/restic" ]]; then
	echo "Local Restic repository is not writable: ${backup_dir}/restic" >&2
	exit 1
fi

if [[ ! -r "${RESTIC_PASSWORD_FILE:-}" ]]; then
	echo "Restic password file is not readable: ${RESTIC_PASSWORD_FILE:-unset}" >&2
	exit 1
fi

cd "$deployment_dir"
exec docker compose --env-file "$env_file" --profile backup run --rm backup
