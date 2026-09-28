#!/usr/bin/env bash
# Exercise macOS host setup without touching Docker or the production paths.
set -euo pipefail

deployment_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "$deployment_dir/deploy.sh"

test_dir=$(mktemp -d /tmp/rmu-lms-platform-test.XXXXXX)
cleanup() {
	[[ "$test_dir" == /tmp/rmu-lms-platform-test.* ]] || return 1
	rm -rf -- "$test_dir"
}
trap cleanup EXIT

host_os=Darwin
script_dir=$test_dir
env_file="$test_dir/.env"
cp "$deployment_dir/env.example" "$test_dir/env.example"

configure_environment <<< $'\n\n'
[[ $(config_get SITE_NAME) == lms.localhost ]]
[[ $(config_get FRONTEND_BIND) == 127.0.0.1:8080 ]]
[[ $(config_get DB_ROOT_PASSWORD_FILE) == "$test_dir/local-data/secrets/db-root-password" ]]
[[ $(config_get RESTIC_PASSWORD_FILE) == "$test_dir/local-data/secrets/restic-password" ]]
[[ $(config_get BACKUP_DIR) == "$test_dir/local-data/backups" ]]
[[ -s "$test_dir/local-data/secrets/db-root-password" ]]
[[ -s "$test_dir/local-data/secrets/restic-password" ]]
[[ -d "$test_dir/local-data/backups/restic" ]]

compose() { printf '%s\n' "$*"; }
[[ $(install_backup_timer | tail -n 1) == '--profile backup-scheduler up --wait --wait-timeout 180 backup-scheduler' ]]
site_name=lms.localhost
local_port=8080
[[ $(public_check | head -n 1) == 'LMS is available locally at http://127.0.0.1:8080/lms' ]]
backend_bench() {
	if [[ "$1" == list-apps ]]; then
		printf 'payments\nlms\n'
	else
		printf '%s\n' "$*" >> "$test_dir/bench.log"
	fi
}
configure_site
grep -Fq 'set-config host_name http://127.0.0.1:8080' "$test_dir/bench.log"

# Existing Linux defaults remain in place; mock privileged host operations.
host_os=Linux
env_file="$test_dir/linux.env"
cp "$deployment_dir/env.example" "$env_file"
ensure_secret() { [[ "$1" == /etc/rmu-lms/* ]]; }
install() { :; }
getenforce() { printf 'Disabled\n'; }
configure_environment
[[ $(config_get DB_ROOT_PASSWORD_FILE) == /etc/rmu-lms/db-root-password ]]
[[ $(config_get RESTIC_PASSWORD_FILE) == /etc/rmu-lms/restic-password ]]
[[ $(config_get BACKUP_DIR) == /var/backups/rmu-lms ]]
configure_site
grep -Fq 'set-config host_name https://learning.example.org' "$test_dir/bench.log"

echo "macOS and Linux deployment setup checks passed."
