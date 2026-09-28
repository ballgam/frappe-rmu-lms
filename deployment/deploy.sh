#!/usr/bin/env bash
# Fetch a fast-forward source update, build one local image, and deploy RMU LMS.
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "$script_dir/.." && pwd)
env_file="$script_dir/.env"
state_file="$script_dir/.deploy-state"
pending_file="$script_dir/.deploy-pending"

die() { echo "Error: $*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

usage() {
	cat <<'EOF'
Usage: ./deployment/deploy.sh
       ./deployment/deploy.sh --abort-pending

Run this as the user who owns the Git checkout (without sudo). The command
fast-forwards its configured upstream branch, builds the application locally,
and creates or upgrades the site. It asks for the public domain on first use.
--abort-pending returns to the previous image only if migration has not begun.

Prerequisites: Ubuntu 24.04 x86_64, Docker Engine with Compose, sudo access,
and an Apache HTTPS route to the chosen 127.0.0.1 port. The server needs access
to the Git remote, container images, and build dependency repositories.
EOF
}

config_get() {
	local key=$1
	[[ -f "$env_file" ]] || return 0
	sed -n "s/^${key}=//p" "$env_file" | tail -n 1
}

config_set() {
	local key=$1 value=$2 line temporary found=false
	temporary=$(mktemp "${env_file}.XXXXXX")
	chmod 0600 "$temporary"
	while IFS= read -r line || [[ -n "$line" ]]; do
		if [[ "$line" == "$key="* ]]; then
			printf '%s=%s\n' "$key" "$value" >> "$temporary"
			found=true
		else
			printf '%s\n' "$line" >> "$temporary"
		fi
	done < "$env_file"
	if [[ "$found" == false ]]; then
		printf '%s=%s\n' "$key" "$value" >> "$temporary"
	fi
	mv -f "$temporary" "$env_file"
}

compose() {
	env -u LMS_IMAGE -u SITE_NAME -u FRONTEND_BIND -u BACKUP_DIR \
		docker compose --project-name rmu-lms --project-directory "$script_dir" \
		--env-file "$env_file" "$@"
}

valid_domain() {
	[[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$ ]]
}

require_command() {
	command -v "$1" >/dev/null 2>&1 || die "Required command is missing: $1"
}

fetch_source() {
	local branch remote merge_ref source_sha mode=${1:-deploy}
	require_command git
	require_command sudo
	[[ -z $(git -C "$repo_dir" status --porcelain --untracked-files=normal) ]] || \
		die "The checkout has local changes. Commit or resolve them before deploying."

	if [[ "$mode" == abort ]]; then
		[[ -f "$pending_file" ]] || die "There is no pending upgrade to abort."
	elif [[ -e "$pending_file" ]]; then
		step "A previous upgrade is pending; resuming it before fetching more code"
	else
		branch=$(git -C "$repo_dir" symbolic-ref --quiet --short HEAD) || \
			die "The checkout is detached. Check out the deployment branch."
		remote=$(git -C "$repo_dir" config --get "branch.${branch}.remote") || \
			die "Branch ${branch} has no upstream remote."
		merge_ref=$(git -C "$repo_dir" config --get "branch.${branch}.merge") || \
			die "Branch ${branch} has no upstream branch."
		[[ "$remote" != . && "$merge_ref" == refs/heads/* ]] || \
			die "Branch ${branch} must track a remote branch."
		step "Fetching ${remote}/${merge_ref#refs/heads/}"
		git -C "$repo_dir" fetch "$remote" "${merge_ref#refs/heads/}"
		git -C "$repo_dir" merge --ff-only FETCH_HEAD || \
			die "The branch cannot be fast-forwarded. No deployment changes were made."
	fi

	source_sha=$(git -C "$repo_dir" rev-parse HEAD)
	# Start the version of this script that came from the fetched checkout.
	if [[ "$mode" == abort ]]; then
		exec sudo -- "$script_dir/deploy.sh" --abort-stage "$source_sha"
	fi
	exec sudo -- "$script_dir/deploy.sh" --deploy-stage "$source_sha"
}

ensure_secret() {
	local path=$1
	[[ "$path" == /etc/rmu-lms/* && "$path" != *'..'* && "$path" != *$'\n'* ]] || \
		die "Secret path must be below /etc/rmu-lms: $path"
	install -d -m 0700 "$(dirname -- "$path")"
	if [[ ! -e "$path" ]]; then
		(umask 077; openssl rand -base64 48 > "$path")
	fi
	[[ -f "$path" && ! -L "$path" ]] || die "Secret is not a regular file: $path"
	chmod 0600 "$path"
}

configure_environment() {
	local requested_domain requested_port bind
	if [[ ! -f "$env_file" ]]; then
		step "First-time site configuration"
		read -r -p 'Public LMS domain (for example lms.example.org): ' requested_domain
		valid_domain "$requested_domain" || die "Enter a DNS hostname, without https:// or a path."
		read -r -p 'Local proxy port [8080]: ' requested_port
		requested_port=${requested_port:-8080}
		[[ "$requested_port" =~ ^[0-9]{2,5}$ ]] && (( requested_port >= 1024 && requested_port <= 65535 )) || \
			die "Local proxy port must be between 1024 and 65535."
		cp "$script_dir/env.example" "$env_file"
		chmod 0600 "$env_file"
		config_set SITE_NAME "$requested_domain"
		config_set FRONTEND_BIND "127.0.0.1:${requested_port}"
	fi
	chmod 0600 "$env_file"

	site_name=$(config_get SITE_NAME)
	valid_domain "$site_name" || die "SITE_NAME in .env is not a valid DNS hostname."
	bind=$(config_get FRONTEND_BIND)
	[[ "$bind" =~ ^127\.0\.0\.1:[0-9]{2,5}$ ]] || \
		die "FRONTEND_BIND must use a loopback address, such as 127.0.0.1:8080."
	local_port=${bind##*:}
	backup_dir=$(config_get BACKUP_DIR)
	backup_dir=${backup_dir:-/var/backups/rmu-lms}
	[[ "$backup_dir" == /var/backups/rmu-lms ]] || \
		die "This deployment uses BACKUP_DIR=/var/backups/rmu-lms."
	config_set BACKUP_DIR "$backup_dir"

	ensure_secret "$(config_get DB_ROOT_PASSWORD_FILE)"
	ensure_secret "$(config_get RESTIC_PASSWORD_FILE)"
	install -d -o 0 -g 0 -m 0700 "$backup_dir" "$backup_dir/restic"
}

build_image() {
	local label
	candidate_image="rmu-lms:git-${source_sha}"
	if docker image inspect "$candidate_image" >/dev/null 2>&1; then
		label=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$candidate_image")
		[[ "$label" == "$source_sha" ]] || die "Existing local tag has a different source revision: $candidate_image"
		step "Reusing the local image for ${source_sha}"
	else
		step "Building Frappe, Payments, LMS, ffmpeg, and Shaka locally"
		docker build --pull --platform linux/amd64 \
			--file "$script_dir/Containerfile" \
			--build-arg "IMAGE_SOURCE=local-checkout" \
			--build-arg "IMAGE_REVISION=${source_sha}" \
			--build-arg "IMAGE_VERSION=${source_sha}" \
			--tag "$candidate_image" "$repo_dir"
	fi
	candidate_id=$(docker image inspect --format '{{.Id}}' "$candidate_image")
	step "Checking the built image"
	docker run --rm --pull never --entrypoint /usr/local/sbin/rmu-lms-smoke-image "$candidate_image"
}

site_exists() {
	docker volume inspect rmu-lms_sites >/dev/null 2>&1 || return 1
	docker run --rm --pull never --volume rmu-lms_sites:/site-volume:ro \
		--entrypoint test "$candidate_image" -f "/site-volume/${site_name}/site_config.json" \
		>/dev/null 2>&1
}

another_site_exists() {
	docker volume inspect rmu-lms_sites >/dev/null 2>&1 || return 1
	[[ -n $(docker run --rm --pull never --volume rmu-lms_sites:/site-volume:ro \
		--entrypoint find "$candidate_image" /site-volume -mindepth 2 -maxdepth 2 \
		-name site_config.json -print -quit) ]]
}

start_dependencies() {
	compose config --quiet
	compose pull db redis-cache redis-queue
	compose up --wait --wait-timeout 180 db redis-cache redis-queue
	compose up --no-deps configurator
}

backend_bench() {
	compose run --rm --no-deps -T backend bench --site "$site_name" "$@"
}

configure_site() {
	local installed_apps
	installed_apps=$(backend_bench list-apps)
	if ! grep -Eq '^payments([[:space:]]|$)' <<< "$installed_apps"; then
		step "Installing Payments"
		backend_bench install-app payments
	fi
	installed_apps=$(backend_bench list-apps)
	if ! grep -Eq '^lms([[:space:]]|$)' <<< "$installed_apps"; then
		step "Installing LMS"
		backend_bench install-app lms
	fi
	backend_bench set-config host_name "https://${site_name}"
	backend_bench set-config --parse max_file_size 2147483648
	backend_bench enable-scheduler
	backend_bench execute frappe.db.set_single_value --args '["LMS Settings", "video_packager_mode", "Binary"]'
	backend_bench execute frappe.db.set_single_value --args '["LMS Settings", "video_transcoding_enabled", 1]'
	backend_bench execute frappe.db.set_single_value --args '["LMS Settings", "keep_original_video", 1]'
	backend_bench migrate
	backend_bench clear-cache
}

wait_for_local_site() {
	local attempt
	for (( attempt=1; attempt<=60; attempt++ )); do
		if curl --fail --silent --header "Host: ${site_name}" \
			"http://127.0.0.1:${local_port}/api/method/ping" >/dev/null; then
			return 0
		fi
		sleep 3
	done
	die "Local LMS health check failed. Run: sudo docker compose -f deployment/compose.yaml logs --tail=100 backend"
}

wait_for_services() {
	local attempt service container_id status all_ready
	local services=(db redis-cache redis-queue backend websocket queue-short queue-long scheduler frontend)
	for (( attempt=1; attempt<=100; attempt++ )); do
		all_ready=true
		for service in "${services[@]}"; do
			container_id=$(compose ps -q "$service")
			if [[ -z "$container_id" ]]; then
				all_ready=false
				continue
			fi
			status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null) || {
				all_ready=false
				continue
			}
			if [[ "$status" != healthy && "$status" != running ]]; then
				all_ready=false
			fi
		done
		[[ "$all_ready" == true ]] && return 0
		sleep 3
	done
	die "A service did not become healthy within five minutes. Inspect: sudo docker compose -f deployment/compose.yaml ps"
}

verify_stack() {
	compose up -d
	wait_for_services
	wait_for_local_site
	compose exec -T backend bench --site "$site_name" check-video-pipeline
	compose exec -T queue-long ffmpeg -version >/dev/null
	compose exec -T queue-long ffprobe -version >/dev/null
	compose exec -T queue-long packager --version >/dev/null
	compose ps
}

install_backup_timer() {
	local escaped_repo temporary
	escaped_repo=$(printf '%s' "$repo_dir" | sed 's/[&|\\]/\\&/g')
	temporary=$(mktemp /tmp/rmu-lms-backup.service.XXXXXX)
	sed "s|/opt/rmu-lms|${escaped_repo}|g" "$script_dir/systemd/rmu-lms-backup.service" > "$temporary"
	install -m 0644 "$temporary" /etc/systemd/system/rmu-lms-backup.service
	rm -f "$temporary"
	install -m 0644 "$script_dir/systemd/rmu-lms-backup.timer" /etc/systemd/system/rmu-lms-backup.timer
	systemctl daemon-reload
	systemctl enable --now rmu-lms-backup.timer
}

write_state() {
	local temporary
	temporary=$(mktemp "$script_dir/.deploy-state.XXXXXX")
	chmod 0600 "$temporary"
	printf 'SOURCE_SHA=%q\nIMAGE_ID=%q\n' "$source_sha" "$candidate_id" > "$temporary"
	mv -f "$temporary" "$state_file"
}

write_pending() {
	local temporary
	temporary=$(mktemp "$script_dir/.deploy-pending.XXXXXX")
	chmod 0600 "$temporary"
	printf 'PHASE=%q\nOLD_IMAGE=%q\nNEW_IMAGE=%q\nSOURCE_SHA=%q\nIMAGE_ID=%q\n' \
		"$phase" "$old_image" "$candidate_image" "$source_sha" "$candidate_id" > "$temporary"
	mv -f "$temporary" "$pending_file"
}

public_check() {
	if curl --fail --silent --show-error --max-time 15 \
		"https://${site_name}/api/method/ping" >/dev/null; then
		echo "LMS is available at https://${site_name}/lms"
	else
		echo "LMS is healthy locally at http://127.0.0.1:${local_port}." >&2
		echo "Ask the Apache administrator to route https://${site_name} to that port, including /socket.io/ WebSockets." >&2
	fi
}

first_deploy() {
	local admin_password admin_confirm db_password
	config_set LMS_IMAGE "$candidate_image"
	start_dependencies
	if ! site_exists; then
		step "Creating the Frappe site"
		read -r -s -p 'Choose an Administrator password: ' admin_password
		printf '\n'
		read -r -s -p 'Repeat the Administrator password: ' admin_confirm
		printf '\n'
		[[ -n "$admin_password" && "$admin_password" == "$admin_confirm" ]] || \
			die "Administrator passwords did not match. Rerun to try again."
		db_password=$(<"$(config_get DB_ROOT_PASSWORD_FILE)")
		compose run --rm --no-deps -T backend bench new-site "$site_name" \
			--db-root-password "$db_password" \
			--admin-password "$admin_password" \
			--set-default --mariadb-user-host-login-scope='%'
		unset admin_password admin_confirm db_password
	fi
	step "Configuring the LMS site and video pipeline"
	configure_site
	verify_stack
	step "Creating the first encrypted local backup"
	"$script_dir/scripts/backup-host.sh"
	install_backup_timer
	write_state
	public_check
}

resume_upgrade() {
	local fresh_backup=${1:-false}
	case "$phase" in
		backed_up|maintenance_on|stopped|migrated) ;;
		migrating) die "A migration was interrupted. Do not restart the old image. Inspect the logs and restore the pre-upgrade backup before retrying." ;;
		*) die "Unknown pending deployment phase: $phase" ;;
	esac

	if [[ "$phase" == backed_up ]]; then
		# The old site may have accepted writes since the previous attempt.
		config_set LMS_IMAGE "$old_image"
		if [[ "$fresh_backup" != true ]]; then
			"$script_dir/scripts/backup-host.sh"
		fi
		step "Entering maintenance mode"
		compose exec -T backend bench --site "$site_name" set-maintenance-mode on
		phase=maintenance_on
		write_pending
	fi
	if [[ "$phase" == maintenance_on ]]; then
		step "Stopping request and background processes"
		compose stop frontend queue-short queue-long scheduler websocket backend
		phase=stopped
		write_pending
	fi
	if [[ "$phase" == stopped ]]; then
		config_set LMS_IMAGE "$candidate_image"
		compose up --wait --wait-timeout 180 db redis-cache redis-queue
		compose up --no-deps configurator
		phase=migrating
		write_pending
		step "Migrating the site with the new image"
		backend_bench migrate
		phase=migrated
		write_pending
	fi
	if [[ "$phase" == migrated ]]; then
		config_set LMS_IMAGE "$candidate_image"
		backend_bench set-maintenance-mode off
		step "Starting and checking the upgraded stack"
		verify_stack
		install_backup_timer
		write_state
		rm -f -- "$pending_file"
		public_check
	fi
}

upgrade() {
	old_image=$(config_get LMS_IMAGE)
	[[ -n "$old_image" ]] || die "LMS_IMAGE is missing from .env."
	docker image inspect "$old_image" >/dev/null 2>&1 || \
		die "The previously deployed image is not available locally: $old_image"
	step "Backing up the existing site before migration"
	"$script_dir/scripts/backup-host.sh"
	compose --profile backup run --rm --entrypoint restic backup snapshots --latest 1
	phase=backed_up
	write_pending
	resume_upgrade true
}

abort_pending() {
	local old_id
	[[ -f "$pending_file" ]] || die "There is no pending upgrade to abort."
	# shellcheck disable=SC1090
	source "$pending_file"
	case "$PHASE" in
		backed_up|maintenance_on|stopped) ;;
		*) die "Migration may have started. Restore the verified backup; automatic rollback is unsafe." ;;
	esac
	[[ "$SOURCE_SHA" == "$source_sha" ]] || die "The checkout no longer matches the pending upgrade."
	old_id=$(docker image inspect --format '{{.Id}}' "$OLD_IMAGE" 2>/dev/null) || \
		die "The previous image is missing: $OLD_IMAGE"
	[[ -n "$old_id" ]] || die "The previous image cannot be inspected."
	step "Returning to the previous image before migration"
	config_set LMS_IMAGE "$OLD_IMAGE"
	compose up --wait --wait-timeout 180 db redis-cache redis-queue
	compose up --no-deps configurator
	backend_bench set-maintenance-mode off
	verify_stack
	rm -f -- "$pending_file"
	public_check
}

deploy_as_root() {
	local expected_sha=$1 current_image state_sha='' state_id='' current_id backend_container running_id
	[[ $(uname -m) == x86_64 ]] || die "This image currently supports x86_64 Ubuntu hosts only."
	[[ $(git -c "safe.directory=$repo_dir" -C "$repo_dir" rev-parse HEAD) == "$expected_sha" ]] || \
		die "The checkout changed after the fetch. Rerun the deployment."
	[[ -z $(git -c "safe.directory=$repo_dir" -C "$repo_dir" status --porcelain --untracked-files=normal) ]] || \
		die "The checkout changed after the fetch. Resolve local changes before deploying."
	for tool in docker git curl openssl sed install systemctl; do require_command "$tool"; done
	docker info >/dev/null 2>&1 || die "Docker Engine is not running or not accessible."
	docker compose version >/dev/null 2>&1 || die "Docker Compose plugin is missing."
	source_sha=$expected_sha
	configure_environment
	build_image

	if [[ -f "$pending_file" ]]; then
		# The file is root-owned state written by this script, not a user input.
		# shellcheck disable=SC1090
		source "$pending_file"
		[[ "$SOURCE_SHA" == "$source_sha" && "$NEW_IMAGE" == "$candidate_image" && "$IMAGE_ID" == "$candidate_id" ]] || \
			die "Pending upgrade does not match this checkout or image. Resolve it before fetching another revision."
		phase=$PHASE
		old_image=$OLD_IMAGE
		resume_upgrade
		return
	fi

	current_image=$(config_get LMS_IMAGE)
	if ! site_exists; then
		[[ ! -f "$state_file" && ( "$current_image" == rmu-lms:unbuilt || "$current_image" == "$candidate_image" ) ]] || \
			die "The configured site is missing. Restore its data or configuration before proceeding."
		another_site_exists && die "The sites volume contains a different site. Check SITE_NAME before proceeding."
		first_deploy
		return
	fi
	[[ "$current_image" != rmu-lms:unbuilt ]] || \
		die "A site already exists, but .env has no deployed image. Recover the previous configuration before proceeding."

	if [[ "$current_image" == "$candidate_image" ]]; then
		if [[ -f "$state_file" ]]; then
			# shellcheck disable=SC1090
			source "$state_file"
			state_sha=$SOURCE_SHA
			state_id=$IMAGE_ID
			[[ "$state_sha" == "$source_sha" && "$state_id" == "$candidate_id" ]] || \
				die "The configured image differs from the completed deployment record. Inspect before proceeding."
			step "This revision is already deployed; checking the stack"
			verify_stack
			public_check
		else
			# A first run created the site but was interrupted before completion.
			first_deploy
		fi
		return
	fi

	current_id=$(docker image inspect --format '{{.Id}}' "$current_image" 2>/dev/null) || \
		die "The configured application image is not available locally: $current_image"
	backend_container=$(compose ps -q backend)
	[[ -n "$backend_container" ]] || die "The existing backend is not running. Inspect it before upgrading."
	running_id=$(docker inspect --format '{{.Image}}' "$backend_container")
	[[ "$running_id" == "$current_id" ]] || \
		die "The running backend does not match LMS_IMAGE in .env. Resolve the drift before upgrading."
	if [[ -f "$state_file" ]]; then
		# shellcheck disable=SC1090
		source "$state_file"
		[[ "$IMAGE_ID" == "$current_id" ]] || \
			die "The configured image does not match the last completed deployment."
	fi

	upgrade
}

main() {
	case "${1:-}" in
		-h|--help) usage ;;
		--abort-stage)
			[[ $# -eq 2 && $EUID -eq 0 ]] || die "Invalid internal abort invocation."
			for tool in docker git curl openssl sed install systemctl; do require_command "$tool"; done
			source_sha=$2
			configure_environment
			abort_pending
			;;
		--deploy-stage)
			[[ $# -eq 2 && $EUID -eq 0 ]] || die "Invalid internal deployment invocation."
			deploy_as_root "$2"
			;;
		'')
			if (( EUID == 0 )); then
				[[ -n ${SUDO_USER:-} && $SUDO_USER != root ]] || \
					die "Run this script as the Git checkout owner, without sudo."
				exec sudo -u "$SUDO_USER" -- "$script_dir/deploy.sh"
			fi
			fetch_source
			;;
		--abort-pending)
			[[ $# -eq 1 ]] || die "Unknown argument after --abort-pending."
			if (( EUID == 0 )); then
				[[ -n ${SUDO_USER:-} && $SUDO_USER != root ]] || \
					die "Run this script as the Git checkout owner, without sudo."
				exec sudo -u "$SUDO_USER" -- "$script_dir/deploy.sh" --abort-pending
			fi
			fetch_source abort
			;;
		*) die "Unknown argument: $1" ;;
	esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	main "$@"
fi
