#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
deployment_dir=$(cd -- "${script_dir}/.." && pwd)
env_file="${deployment_dir}/.env"

if [[ ! -f "$env_file" ]]; then
	echo "Missing deployment environment file: ${env_file}" >&2
	exit 1
fi

config_get() {
	sed -n "s/^${1}=//p" "$env_file" | tail -n 1
}

if [[ $(uname -s) == Darwin ]]; then
	expected_backup_dir="${deployment_dir}/local-data/backups"
else
	expected_backup_dir=/var/backups/rmu-lms
fi
backup_dir=$(config_get BACKUP_DIR)
backup_dir=${backup_dir:-$expected_backup_dir}
if [[ "$backup_dir" != "$expected_backup_dir" ]]; then
	echo "BACKUP_DIR must be ${expected_backup_dir}." >&2
	exit 1
fi

if [[ ! -d "$backup_dir/restic" || ! -w "$backup_dir/restic" ]]; then
	echo "Local Restic repository is not writable: ${backup_dir}/restic" >&2
	exit 1
fi

restic_password_file=$(config_get RESTIC_PASSWORD_FILE)
if [[ ! -r "$restic_password_file" ]]; then
	echo "Restic password file is not readable: ${restic_password_file:-unset}" >&2
	exit 1
fi

cd "$deployment_dir"
exec env -u LMS_IMAGE -u SITE_NAME -u FRONTEND_BIND -u BACKUP_DIR \
	-u DB_ROOT_PASSWORD_FILE -u RESTIC_PASSWORD_FILE -u RESTIC_REPOSITORY -u BACKUP_TAG \
	"$script_dir/compose-cli.sh" --project-name rmu-lms \
	--file "$deployment_dir/compose.yaml" --env-file "$env_file" \
	--profile backup run --rm backup
