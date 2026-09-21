# RMU LMS production commands

This is the short, ordered installation path for a fresh Ubuntu 24.04 x86_64 server. The detailed explanations, recovery procedure, and troubleshooting remain in [`deployment/README.md`](deployment/README.md).

Before starting:

- Know the production hostname that the externally managed proxy will publish.
- Publish a GitHub Release and copy the image digest from the workflow summary.
- Configure the remote backup filesystem in `/etc/fstab`.
- Arrange HTTPS and reverse-proxy configuration separately; this guide does not change Apache.
- Replace the example values below.

## 1. Set deployment values

Run these commands on the server as your normal sudo-enabled user:

```bash
export LMS_DOMAIN=learning.example.org
export GHCR_USER=GITHUB_MACHINE_USER
export IMAGE_DIGEST=sha256:REPLACE_WITH_RELEASE_DIGEST
export BACKUP_MOUNT=/mnt/rmu-lms-backups
```

## 2. Install Docker and host tools

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git openssl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
  jq util-linux

sudo systemctl enable --now docker

sudo docker version
sudo docker compose version
```

## 3. Get the deployment files

```bash
sudo install -d -o "$USER" -g "$USER" /opt/rmu-lms
git clone https://github.com/RMU-Somalia/frappe-lms.git /opt/rmu-lms
cd /opt/rmu-lms/deployment
```

Use the repository's deploy key when the source repository is private.

## 4. Log in to private GHCR

Use a classic GitHub PAT with only `read:packages` and organization SSO authorization when required:

```bash
read -rsp 'GHCR read token: ' GHCR_TOKEN
printf '%s' "$GHCR_TOKEN" | \
  sudo docker login ghcr.io --username "$GHCR_USER" --password-stdin
unset GHCR_TOKEN
```

## 5. Create secrets and `.env`

```bash
sudo install -d -m 0700 /etc/rmu-lms
sudo sh -c 'umask 077; openssl rand -base64 48 > /etc/rmu-lms/db-root-password'
sudo sh -c 'umask 077; openssl rand -base64 48 > /etc/rmu-lms/restic-password'
sudo chmod 0600 /etc/rmu-lms/db-root-password /etc/rmu-lms/restic-password

cp env.example .env
sed -i "s|^LMS_IMAGE=.*|LMS_IMAGE=ghcr.io/rmu-somalia/frappe-lms@${IMAGE_DIGEST}|" .env
sed -i "s|^SITE_NAME=.*|SITE_NAME=${LMS_DOMAIN}|" .env
sed -i "s|^BACKUP_MOUNT=.*|BACKUP_MOUNT=${BACKUP_MOUNT}|" .env
chmod 0600 .env

sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env pull
```

## 6. Start dependencies and create the site

```bash
sudo docker compose --env-file .env up -d db redis-cache redis-queue configurator
sudo docker compose --env-file .env up -d \
  backend websocket queue-short queue-long scheduler

set -a
source .env
set +a

sudo docker compose --env-file .env exec backend \
  bench new-site "$SITE_NAME" \
  --set-default \
  --mariadb-user-host-login-scope='%'
```

At the prompt, use the MariaDB password stored in `/etc/rmu-lms/db-root-password`, then choose a separate Administrator password. Retrieve the database password in another terminal if needed:

```bash
sudo cat /etc/rmu-lms/db-root-password
```

Install and configure the applications:

```bash
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" install-app payments
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" install-app lms

sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" set-config host_name "https://$SITE_NAME"
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" set-config --parse max_file_size 2147483648
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" enable-scheduler

sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" execute frappe.db.set_single_value \
  --args '["LMS Settings", "video_packager_mode", "Binary"]'
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" execute frappe.db.set_single_value \
  --args '["LMS Settings", "video_transcoding_enabled", 1]'
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" execute frappe.db.set_single_value \
  --args '["LMS Settings", "keep_original_video", 1]'

sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" migrate
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" list-apps
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" check-video-pipeline
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" clear-cache

sudo docker compose --env-file .env up -d
sudo docker compose --env-file .env ps
curl --fail --header "Host: $SITE_NAME" \
  http://127.0.0.1:8080/api/method/ping
```

The external HTTPS/reverse-proxy configuration must send traffic to `127.0.0.1:8080`, preserve the original `Host`, set `X-Forwarded-Proto: https`, support WebSocket upgrades on `/socket.io/`, and allow 2 GB requests with long upload timeouts.

## 7. Initialize encrypted remote backups

The mount command expects an `/etc/fstab` entry for `BACKUP_MOUNT`:

```bash
sudo mkdir -p "$BACKUP_MOUNT"
sudo mount "$BACKUP_MOUNT"
mountpoint "$BACKUP_MOUNT"
sudo install -d -o 1000 -g 1000 -m 0700 "$BACKUP_MOUNT/restic"

cd /opt/rmu-lms/deployment
sudo ./scripts/backup-host.sh

sudo install -m 0644 systemd/rmu-lms-backup.service /etc/systemd/system/
sudo install -m 0644 systemd/rmu-lms-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rmu-lms-backup.timer
sudo systemctl list-timers rmu-lms-backup.timer
```

## 8. Final checks

```bash
cd /opt/rmu-lms/deployment
sudo docker compose --env-file .env ps
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" check-video-pipeline
sudo docker compose --env-file .env logs --tail=100 queue-long scheduler
sudo ss -lntp | grep '127.0.0.1:8080'
```

Complete the multi-audio upload, later-audio addition, progressive fallback, private-media access, and restart tests in the main runbook.

## 9. Deploy a later release

Set the new digest, back up, migrate once, and restart:

```bash
export NEW_IMAGE_DIGEST=sha256:REPLACE_WITH_NEW_RELEASE_DIGEST
cd /opt/rmu-lms/deployment
set -a
source .env
set +a

sudo ./scripts/backup-host.sh
grep '^LMS_IMAGE=' .env
sed -i "s|^LMS_IMAGE=.*|LMS_IMAGE=ghcr.io/rmu-somalia/frappe-lms@${NEW_IMAGE_DIGEST}|" .env
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env pull

sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" set-maintenance-mode on
sudo docker compose --env-file .env stop \
  frontend queue-short queue-long scheduler websocket backend
sudo docker compose --env-file .env up -d db redis-cache redis-queue configurator
sudo docker compose --env-file .env run --rm backend \
  bench --site "$SITE_NAME" migrate

sudo docker compose --env-file .env up -d
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" set-maintenance-mode off
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" check-video-pipeline
sudo docker compose --env-file .env ps
curl --fail --header "Host: $SITE_NAME" \
  http://127.0.0.1:8080/api/method/ping
```

If migration fails, do not start the previous image against the migrated database. Follow the restore-based rollback in `deployment/README.md`.
