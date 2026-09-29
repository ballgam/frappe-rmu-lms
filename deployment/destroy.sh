#!/usr/bin/env bash
# Permanently remove the RMU LMS deployment, data, backups, and secrets.
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "$script_dir/.." && pwd)
host_os=$(uname -s)
env_file="$script_dir/.env"
state_file="$script_dir/.deploy-state"
pending_file="$script_dir/.deploy-pending"
project_name=rmu-lms
assume_yes=false
remove_apache=false

die() { echo "Error: $*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }
warn() { echo "Warning: $*" >&2; }

usage() {
	cat <<'EOF'
Usage: ./deployment/destroy.sh [--yes] [--remove-apache]

Permanently removes the RMU LMS deployment from this host: containers,
networks, named volumes (site files, database, persistent queue), locally
built images, the backup systemd timer, secrets, encrypted backups, and the
deployment state files. There is no undo.

Run as the checkout owner on macOS, or with sudo on Linux.

  -y, --yes         skip the typed confirmation (for automation)
      --remove-apache  also disable the Apache vhost and delete its certificate
EOF
}

config_get() {
	[[ -f "$env_file" ]] || return 0
	sed -n "s/^${1}=//p" "$env_file" | tail -n 1
}

require_command() {
	command -v "$1" >/dev/null 2>&1 || die "Required command is missing: $1"
}

confirm_destruction() {
	local answer
	if [[ "$assume_yes" == true ]]; then
		warn "Proceeding without confirmation because --yes was given."
		return
	fi
	cat >&2 <<EOF
This permanently deletes the RMU LMS deployment:
  - containers, network, and volumes (site files, database, queue)
  - local images tagged rmu-lms*
  - secrets under ${secret_dir}
  - encrypted backups under ${backup_dir}
  - ${env_file}, ${state_file}, and ${pending_file}
EOF
	if [[ "$remove_apache" == true ]]; then
		echo "  - the Apache vhost and TLS certificate" >&2
	elif [[ -n "$site_name" ]]; then
		echo "Run with --remove-apache to also remove the Apache vhost and certificate." >&2
	fi
	echo "If any data must survive, cancel now and copy a backup off this host first." >&2
	printf "Type 'destroy' to continue: " >&2
	IFS= read -r answer || die "No confirmation received."
	[[ "$answer" == destroy ]] || die "Confirmation did not match. Nothing was removed."
}

remove_compose_stack() {
	local containers volumes
	if [[ -f "$env_file" ]] && "$script_dir/scripts/compose-cli.sh" version >/dev/null 2>&1; then
		if "$script_dir/scripts/compose-cli.sh" \
			--project-name "$project_name" --project-directory "$script_dir" \
			--file "$script_dir/compose.yaml" --env-file "$env_file" \
			--profile backup --profile backup-scheduler \
			down --volumes --remove-orphans; then
			return 0
		fi
		warn "Compose teardown failed; removing containers and volumes directly."
	fi
	containers=$(docker ps -aq --filter "label=com.docker.compose.project=${project_name}" || true)
	if [[ -n "$containers" ]]; then
		docker rm -f $containers || warn "Some containers could not be removed."
	fi
	docker network rm "${project_name}_default" >/dev/null 2>&1 || true
	volumes=$(docker volume ls -q --filter "label=com.docker.compose.project=${project_name}" || true)
	if [[ -n "$volumes" ]]; then
		docker volume rm $volumes >/dev/null 2>&1 || warn "Some volumes could not be removed."
	fi
	local volume
	for volume in "${project_name}_sites" "${project_name}_db-data" "${project_name}_redis-queue-data"; do
		docker volume rm "$volume" >/dev/null 2>&1 || true
	done
}

remove_images() {
	local images
	images=$(docker images --filter reference='rmu-lms*' -q || true)
	if [[ -n "$images" ]]; then
		docker rmi -f $images || warn "Some local images could not be removed."
	fi
	if docker images --format '{{.Repository}}' | grep -qi 'ghcr.io/.*lms'; then
		warn "A former GHCR image may remain locally; remove it with docker rmi."
	fi
}

remove_systemd_units() {
	[[ "$host_os" == Linux ]] || return 0
	systemctl disable --now rmu-lms-backup.timer >/dev/null 2>&1 || true
	rm -f /etc/systemd/system/rmu-lms-backup.service \
		/etc/systemd/system/rmu-lms-backup.timer
	systemctl daemon-reload >/dev/null 2>&1 || true
	systemctl reset-failed rmu-lms-backup.service rmu-lms-backup.timer >/dev/null 2>&1 || true
}

remove_apache_route() {
	[[ "$remove_apache" == true ]] || return 0
	step "Removing the Apache route and certificate"
	if command -v a2dissite >/dev/null 2>&1; then
		a2dissite rmu-lms >/dev/null 2>&1 || true
	fi
	rm -f /etc/apache2/sites-enabled/rmu-lms.conf \
		/etc/apache2/sites-available/rmu-lms.conf \
		/etc/httpd/conf.d/rmu-lms.conf
	if [[ -n "$site_name" ]] && command -v certbot >/dev/null 2>&1; then
		certbot delete --cert-name "$site_name" --non-interactive || \
			warn "Could not delete the certificate for ${site_name}."
	fi
	if command -v apachectl >/dev/null 2>&1; then
		apachectl configtest >/dev/null 2>&1 || warn "Apache configuration test failed."
		systemctl reload apache2 >/dev/null 2>&1 || \
			systemctl reload httpd >/dev/null 2>&1 || \
			warn "Could not reload Apache; reload it manually."
	fi
}

remove_local_state() {
	step "Removing secrets, backups, and deployment state"
	if [[ "$host_os" == Darwin ]]; then
		rm -rf "$script_dir/local-data"
	else
		rm -rf /etc/rmu-lms "$backup_dir"
	fi
	rm -f "$env_file" "$state_file" "$pending_file"
}

main() {
	local arg
	for arg in "$@"; do
		case "$arg" in
			-h|--help) usage; return 0 ;;
			-y|--yes) assume_yes=true ;;
			--remove-apache) remove_apache=true ;;
			*) die "Unknown argument: $arg" ;;
		esac
	done
	[[ "$host_os" == Linux || "$host_os" == Darwin ]] || die "Unsupported host OS: $host_os"
	if [[ "$host_os" == Linux ]]; then
		(( EUID == 0 )) || exec sudo -- "$script_dir/destroy.sh" "$@"
	else
		(( EUID != 0 )) || die "Run this script as your Docker Desktop user, without sudo."
	fi
	require_command docker
	require_command sed
	docker info >/dev/null 2>&1 || die "Docker Engine is not running or not accessible."

	site_name=$(config_get SITE_NAME)
	backup_dir=$(config_get BACKUP_DIR)
	if [[ "$host_os" == Darwin ]]; then
		secret_dir="$script_dir/local-data/secrets"
		backup_dir=${backup_dir:-"$script_dir/local-data/backups"}
	else
		secret_dir=/etc/rmu-lms
		backup_dir=${backup_dir:-/var/backups/rmu-lms}
		require_command systemctl
	fi

	confirm_destruction
	step "Stopping and removing containers and volumes"
	remove_compose_stack
	step "Removing local images"
	remove_images
	step "Removing the backup timer and units"
	remove_systemd_units
	remove_apache_route
	remove_local_state

	step "Removal complete"
	echo "The RMU LMS deployment was removed from this host."
	echo "Remaining manual steps:"
	if [[ -n "$site_name" ]]; then
		echo "  - remove the DNS record for ${site_name}"
	fi
	if [[ "$host_os" == Linux && "$remove_apache" != true ]]; then
		echo "  - remove the Apache vhost and certificate (see deployment/apache/README.md)"
	fi
	echo "  - delete the source checkout: rm -rf ${repo_dir}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	main "$@"
fi
