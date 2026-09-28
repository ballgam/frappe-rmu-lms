#!/usr/bin/env bash
set -euo pipefail

: "${SITE_NAME:?SITE_NAME is required}"
: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY is required}"
: "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE is required}"
: "${BACKUP_TAG:=rmu-lms}"

bench_root=/home/frappe/frappe-bench
site_root="${bench_root}/sites/${SITE_NAME}"

if [[ ! -f "${site_root}/site_config.json" ]]; then
	echo "Site does not exist in the shared volume: ${SITE_NAME}" >&2
	exit 1
fi

if [[ ! -r "$RESTIC_PASSWORD_FILE" ]]; then
	echo "Restic password file is not readable: ${RESTIC_PASSWORD_FILE}" >&2
	exit 1
fi

staging_dir=$(mktemp -d /tmp/rmu-lms-backup.XXXXXX)
if [[ $(id -u) -eq 0 ]]; then
	chown frappe:frappe "$staging_dir"
fi
cleanup() {
	rm -rf "$staging_dir"
}
trap cleanup EXIT INT TERM

cd "$bench_root"

echo "Creating logical database and site-configuration backup for ${SITE_NAME}..."
if [[ $(id -u) -eq 0 ]]; then
	runuser -u frappe -- bench --site "$SITE_NAME" backup --backup-path "$staging_dir"
else
	bench --site "$SITE_NAME" backup --backup-path "$staging_dir"
fi

if ! restic cat config >/dev/null 2>&1; then
	if [[ -e "${RESTIC_REPOSITORY}/config" ]]; then
		echo "Restic repository exists but cannot be opened; check its password and permissions." >&2
		exit 1
	fi
	echo "Initializing encrypted Restic repository at ${RESTIC_REPOSITORY}..."
	restic init
fi

echo "Snapshotting database, configuration, uploads, and completed DASH packages..."
restic backup \
	--host "${SITE_NAME}" \
	--tag "${BACKUP_TAG}" \
	--tag "${LMS_IMAGE:-unknown-image}" \
	--exclude "${site_root}/logs" \
	--exclude "${site_root}/locks" \
	--exclude "${site_root}/indexes" \
	--exclude "${site_root}/private/backups" \
	--exclude "${site_root}/private/files/videos/.tmp" \
	--exclude "${site_root}/public/files/videos/.tmp" \
	"$staging_dir" \
	"${bench_root}/sites/common_site_config.json" \
	"${site_root}/site_config.json" \
	"${site_root}/public/files" \
	"${site_root}/private/files"

echo "Checking repository metadata..."
restic check

echo "Applying retention: last 3, 7 daily, 4 weekly, 6 monthly snapshots..."
restic forget \
	--host "${SITE_NAME}" \
	--tag "${BACKUP_TAG}" \
	--keep-last 3 \
	--keep-daily 7 \
	--keep-weekly 4 \
	--keep-monthly 6 \
	--prune

echo "Backup completed successfully."
