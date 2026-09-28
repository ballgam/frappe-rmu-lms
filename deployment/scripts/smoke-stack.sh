#!/usr/bin/env bash
set -euo pipefail

image=${1:-rmu-lms:smoke}
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
deployment_dir=$(cd -- "${script_dir}/.." && pwd)
compose_file="${deployment_dir}/compose.yaml"
state_dir=$(mktemp -d /tmp/rmu-lms-stack-smoke.XXXXXX)
project_name="rmu-lms-smoke-${GITHUB_RUN_ID:-local}-$$"

cleanup() {
	"$script_dir/compose-cli.sh" --project-name "$project_name" --file "$compose_file" down \
		--volumes --remove-orphans >/dev/null 2>&1 || true
	rm -rf "$state_dir"
}
trap cleanup EXIT INT TERM

install -d -m 0700 "${state_dir}/backup"
printf '%s\n' 'stack-smoke-db-root-password' > "${state_dir}/db-root-password"
printf '%s\n' 'stack-smoke-restic-password' > "${state_dir}/restic-password"
chmod 0600 "${state_dir}/db-root-password" "${state_dir}/restic-password"

export LMS_IMAGE="$image"
export SITE_NAME=smoke.localhost
export FRONTEND_BIND=127.0.0.1:18080
export DB_ROOT_PASSWORD_FILE="${state_dir}/db-root-password"
export RESTIC_PASSWORD_FILE="${state_dir}/restic-password"
export BACKUP_DIR="${state_dir}/backup"
export RESTIC_REPOSITORY=/backup/restic

compose=("$script_dir/compose-cli.sh" --project-name "$project_name" --file "$compose_file")

echo "Starting disposable MariaDB and Redis services..."
"${compose[@]}" up --detach --wait db redis-cache redis-queue
"${compose[@]}" up --no-deps configurator

run_backend() {
	"${compose[@]}" run --rm --no-deps backend "$@"
}

echo "Creating disposable Frappe site..."
run_backend bench new-site "$SITE_NAME" \
	--db-root-password stack-smoke-db-root-password \
	--admin-password stack-smoke-admin-password \
	--mariadb-user-host-login-scope='%' \
	--set-default

echo "Installing Payments and LMS..."
run_backend bench --site "$SITE_NAME" install-app payments
run_backend bench --site "$SITE_NAME" install-app lms
run_backend bench --site "$SITE_NAME" execute frappe.db.set_single_value \
	--args '["LMS Settings", "video_packager_mode", "Binary"]'

echo "Migrating and checking the site..."
run_backend bench --site "$SITE_NAME" migrate
installed_apps=$(run_backend bench --site "$SITE_NAME" list-apps)
grep -q 'payments' <<<"$installed_apps"
grep -q 'lms' <<<"$installed_apps"
run_backend bench --site "$SITE_NAME" check-video-pipeline

echo "Disposable stack smoke test passed."
