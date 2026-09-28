#!/usr/bin/env bash
# Focused checks for the upgrade boundary; Docker calls are deliberately mocked.
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "$script_dir/../deploy.sh"

test_dir=$(mktemp -d /tmp/rmu-lms-deploy-test.XXXXXX)
env_file="$test_dir/.env"
state_file="$test_dir/.deploy-state"
pending_file="$test_dir/.deploy-pending"
log_file="$test_dir/operations.log"
cleanup() {
	rm -f -- "$env_file" "$state_file" "$pending_file" "$log_file"
	rmdir -- "$test_dir"
}
trap cleanup EXIT

printf 'LMS_IMAGE=rmu-lms:old\nSITE_NAME=lms.example.org\n' > "$env_file"
: > "$log_file"
source_sha=0123456789abcdef0123456789abcdef01234567
candidate_image="rmu-lms:git-${source_sha}"
candidate_id="sha256:abcdef"
old_image=rmu-lms:old
site_name=lms.example.org
phase=backed_up

record() { printf '%s\n' "$*" >> "$log_file"; }
compose() { record "compose $*"; }
backend_bench() { record "bench $*"; }
verify_stack() { record verify-stack; }
install_backup_timer() { record install-timer; }
public_check() { record public-check; }

# A fresh backup must lead to exactly one migration and a completed record.
resume_upgrade true
[[ $(config_get LMS_IMAGE) == "$candidate_image" ]]
[[ -f "$state_file" && ! -f "$pending_file" ]]
[[ $(grep -c '^bench migrate$' "$log_file") -eq 1 ]]
grep -q '^compose exec -T backend bench --site lms.example.org set-maintenance-mode on$' "$log_file"
grep -q '^bench set-maintenance-mode off$' "$log_file"

# A retry after migration only starts and verifies; it never migrates twice.
: > "$log_file"
phase=migrated
resume_upgrade
! grep -q '^bench migrate$' "$log_file"
grep -q '^verify-stack$' "$log_file"

# An interrupted migration requires manual recovery.
phase=migrating
if (resume_upgrade) >/dev/null 2>&1; then
	echo "Interrupted migration unexpectedly resumed." >&2
	exit 1
fi

# Before migration begins, the previous image can be restarted safely.
: > "$log_file"
phase=stopped
write_pending
config_set LMS_IMAGE "$candidate_image"
docker() { printf 'sha256:old-image\n'; }
abort_pending
[[ $(config_get LMS_IMAGE) == "$old_image" && ! -f "$pending_file" ]]
grep -q '^bench set-maintenance-mode off$' "$log_file"
! grep -q '^bench migrate$' "$log_file"

echo "Deployment state checks passed."
