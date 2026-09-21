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

if [[ -z "${BACKUP_MOUNT:-}" || "$BACKUP_MOUNT" == "/" || "$BACKUP_MOUNT" != /* ]]; then
	echo "BACKUP_MOUNT must be a non-root absolute path." >&2
	exit 1
fi

if ! mountpoint --quiet -- "$BACKUP_MOUNT"; then
	echo "Remote backup filesystem is not mounted: ${BACKUP_MOUNT}" >&2
	exit 1
fi

if [[ ! -r "${RESTIC_PASSWORD_FILE:-}" ]]; then
	echo "Restic password file is not readable: ${RESTIC_PASSWORD_FILE:-unset}" >&2
	exit 1
fi

cd "$deployment_dir"
exec docker compose --env-file "$env_file" --profile backup run --rm backup

