# RMU Somalia Frappe Learning: manual production hosting

This directory is the production runbook for the customized RMU Somalia / UN Frappe Learning system. It deploys one immutable application image across the standard Frappe processes and keeps all live state outside the image.

The deployment is intentionally independent of `apps/lms/deploy/`. Do not mix files or commands from that directory into this stack.

## Architecture and limits

The supported production shape is one Ubuntu 24.04 x86_64 Docker host:

```text
Internet
   |
Apache :80/:443 (TLS, 2 GB request limit, WebSocket proxy)
   |
127.0.0.1:8080
   |
Frappe frontend Nginx
   +-- Gunicorn backend
   +-- Socket.IO

Docker-only network
   +-- short/default worker
   +-- long worker pool (2 processes: ffmpeg + Shaka Packager)
   +-- scheduler (exactly one)
   +-- MariaDB 10.11
   +-- Redis cache
   +-- persistent Redis queue
```

Start with at least 16 vCPU, 32 GB RAM, and 1 TB of NVMe storage. The long-worker container is limited to eight CPUs and 12 GB RAM, leaving capacity for the web and database services.

The DASH pipeline requires a shared POSIX filesystem. It uses file locks, sibling staging directories, and atomic renames of `manifest.mpd`; do not move the site volume to object storage or distribute these containers across hosts.

Uploaded files are currently buffered by Frappe. A 2 GB upload can cause roughly a 2 GB web-worker memory spike. The default of two Gunicorn workers deliberately caps simultaneous spikes. Chunked/resumable uploads are not implemented by this deployment.

Keep at least three times the expected source-video volume available for sources, normalized media, DASH segments, posters, and staging. Backups need separate remote capacity.

## What is pinned in the image

- Frappe 15.116.1, Payments, and LMS are copied from this repository's checked-in sources.
- Python 3.12.12 base image is pinned by digest.
- Node.js 22.22.0, Shaka Packager 3.9.3, and wkhtmltopdf 0.12.6.1-3 are verified by SHA-256 during the build.
- MariaDB 10.11 and Redis 7.2 images are pinned by digest in `compose.yaml`.
- `ffmpeg` and `ffprobe` are installed in the application image.
- Shaka runs as `/usr/local/bin/packager` in **Binary** mode. The Docker socket is never mounted.

Production must not run `bench update`, `bench get-app`, or pull Git branches inside a container. Create a new repository release and deploy its image digest instead.

## 1. Prepare DNS and the server

Create an A/AAAA record for the production hostname before requesting a certificate. The examples use `learning.example.org`; substitute the real hostname everywhere.

Install Docker Engine and its Compose plugin from Docker's official Ubuntu repository. Confirm:

```bash
docker version
docker compose version
```

Install the host services and tools:

```bash
sudo apt update
sudo apt install -y apache2 jq util-linux ufw
sudo a2enmod headers proxy proxy_http rewrite ssl
```

The backup guard uses `mountpoint`, which is supplied by `util-linux`.

Allow only SSH and public web traffic:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Apache Full'
sudo ufw enable
sudo ufw status
```

Do not expose ports 3306, 6379, 8000, 8080, or 9000. Compose binds its frontend to `127.0.0.1:8080` only.

Place the repository at the path used by the systemd unit:

```bash
sudo git clone https://github.com/RMU-Somalia/frappe-lms.git /opt/rmu-lms
sudo chown -R "$USER":"$USER" /opt/rmu-lms
cd /opt/rmu-lms/deployment
```

For a private source repository, clone with your normal deploy key. The source checkout is used only for configuration and scripts on the server; application code comes from GHCR.

## 2. Publish and authorize the private GHCR image

The workflow at `.github/workflows/publish-deployment-image.yml` runs only when a GitHub Release is published. It builds `linux/amd64`, smoke-tests the runtime, publishes the release and commit tags, creates a provenance attestation, and prints the immutable digest in the Actions job summary.

Recommended release tags follow this form:

```text
v1.0.0-rmu.1
```

The workflow publishes:

```text
ghcr.io/rmu-somalia/frappe-lms:v1.0.0-rmu.1
ghcr.io/rmu-somalia/frappe-lms:sha-<full-git-commit>
```

It intentionally does not publish `latest`.

After the first publish, open the package settings in GitHub:

1. Keep package visibility **Private**.
2. Confirm the package is linked to `RMU-Somalia/frappe-lms`.
3. Under **Manage Actions access**, grant this repository write access if it was not inherited automatically.

For the server, create a classic personal access token on a dedicated machine/deploy account with only `read:packages`. Authorize organization SSO if RMU-Somalia requires it. Log in without placing the token in shell history:

```bash
read -rsp 'GHCR read token: ' CR_PAT
printf '%s' "$CR_PAT" | sudo docker login ghcr.io -u GITHUB_MACHINE_USER --password-stdin
unset CR_PAT
```

Public GHCR images can be pulled anonymously, but this deployment assumes the image remains private.

### Emergency manual publish

Prefer GitHub Releases. If Actions is unavailable, a user with a classic `write:packages` token can run:

```bash
cd /opt/rmu-lms
export RELEASE_TAG=v1.0.0-rmu.1
export RELEASE_SHA=$(git rev-parse HEAD)

docker build \
  --platform linux/amd64 \
  --file deployment/Containerfile \
  --build-arg "IMAGE_SOURCE=https://github.com/RMU-Somalia/frappe-lms" \
  --build-arg "IMAGE_REVISION=$RELEASE_SHA" \
  --build-arg "IMAGE_VERSION=$RELEASE_TAG" \
  --tag "ghcr.io/rmu-somalia/frappe-lms:$RELEASE_TAG" \
  --tag "ghcr.io/rmu-somalia/frappe-lms:sha-$RELEASE_SHA" \
  .

docker run --rm --entrypoint /usr/local/sbin/rmu-lms-smoke-image \
  "ghcr.io/rmu-somalia/frappe-lms:$RELEASE_TAG"
docker push "ghcr.io/rmu-somalia/frappe-lms:$RELEASE_TAG"
docker push "ghcr.io/rmu-somalia/frappe-lms:sha-$RELEASE_SHA"
```

Record the pushed digest from `docker inspect` and deploy `name@sha256:digest`, not the mutable tag.

## 3. Create configuration and secrets

Copy and edit the environment template:

```bash
cd /opt/rmu-lms/deployment
cp env.example .env
chmod 0600 .env
editor .env
```

Set at minimum:

- `LMS_IMAGE` to the exact digest from the release job summary.
- `SITE_NAME` to the public DNS name.
- `BACKUP_MOUNT` to the mounted remote filesystem.
- The two host-side secret paths.

Create secrets without echoing them to the terminal:

```bash
sudo install -d -m 0700 /etc/rmu-lms
sudo sh -c 'umask 077; openssl rand -base64 48 > /etc/rmu-lms/db-root-password'
sudo sh -c 'umask 077; openssl rand -base64 48 > /etc/rmu-lms/restic-password'
sudo chmod 0600 /etc/rmu-lms/db-root-password /etc/rmu-lms/restic-password
```

Keep both files in the server's secrets manager. The MariaDB password is also needed interactively during initial site creation and disaster recovery. The Restic password is required to read any backup; losing it makes every snapshot unrecoverable.

The secret files are root-only, so production Compose commands in this runbook use `sudo`. The GHCR login above is likewise stored for root's Docker client. Do not relax the files to world-readable permissions merely to run Compose without `sudo`.

Validate configuration before changing runtime state:

```bash
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env pull
```

## 4. Start dependencies and create the site

Start stateful dependencies and run the idempotent configurator:

```bash
cd /opt/rmu-lms/deployment
sudo docker compose --env-file .env up -d db redis-cache redis-queue configurator
sudo docker compose --env-file .env ps
```

Start the application processes. The backend health check can remain unhealthy until the first site exists; this is expected.

```bash
sudo docker compose --env-file .env up -d backend websocket queue-short queue-long scheduler
```

Load the configured hostname for subsequent commands:

```bash
set -a
source .env
set +a
```

Create the site interactively. Enter the value stored in `/etc/rmu-lms/db-root-password` when Bench asks for the MariaDB root password. Choose a strong, separate Administrator password when prompted.

```bash
sudo docker compose --env-file .env exec backend \
  bench new-site "$SITE_NAME" \
  --set-default \
  --mariadb-user-host-login-scope='172.%.%.%'
```

Install Payments before LMS:

```bash
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" install-app payments
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" install-app lms
```

Apply the production site configuration:

```bash
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
```

Migrate and verify the installed system:

```bash
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" migrate
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" list-apps
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" check-video-pipeline
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" clear-cache
```

`check-video-pipeline` must report usable `ffmpeg`, `ffprobe`, and Packager paths before instructors upload lectures.

Start or reconcile the complete stack:

```bash
sudo docker compose --env-file .env up -d
sudo docker compose --env-file .env ps
curl --fail --header "Host: $SITE_NAME" http://127.0.0.1:8080/api/method/ping
```

## 5. Configure Apache and TLS

Enable the temporary HTTP proxy so Certbot can validate the hostname:

```bash
cd /opt/rmu-lms/deployment
sed "s/LMS_DOMAIN/$SITE_NAME/g" apache/rmu-lms-http.conf.example | \
  sudo tee /etc/apache2/sites-available/rmu-lms-http.conf >/dev/null
sudo a2ensite rmu-lms-http.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

Install Certbot using its supported snap and request the certificate:

```bash
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/local/bin/certbot
sudo certbot certonly --apache -d "$SITE_NAME"
```

Install the final HTTPS configuration:

```bash
sed "s/LMS_DOMAIN/$SITE_NAME/g" apache/rmu-lms-ssl.conf.example | \
  sudo tee /etc/apache2/sites-available/rmu-lms.conf >/dev/null
sudo a2dissite rmu-lms-http.conf
sudo a2ensite rmu-lms.conf
sudo apachectl configtest
sudo systemctl reload apache2
sudo certbot renew --dry-run
```

Test both application traffic and Socket.IO in browser developer tools:

```bash
curl --fail --silent --show-error "https://$SITE_NAME/api/method/ping"
curl --fail --silent --show-error --head "https://$SITE_NAME/assets/lms/images/lms-logo.png"
```

The Apache template uses `mod_proxy_http` WebSocket upgrades, preserves the original host, sends `X-Forwarded-Proto=https`, allows 2 GB bodies, and uses a 660-second proxy timeout.

## 6. Application smoke test

Before opening enrollment:

1. Sign in as Administrator and open `/lms`.
2. Configure outbound email and Zoom only if those features are required; they are application settings, not stack prerequisites.
3. Upload a short recording containing English and Somali audio tracks.
4. Wait for `LMS Video` to become **Ready** and confirm `manifest.mpd` playback.
5. Switch audio tracks in Shaka Player.
6. Add a translated audio file later and verify the video is not re-encoded.
7. Verify a legacy/unpackaged progressive video still plays.
8. Open the private manifest or segment URL in an unauthenticated browser and confirm access is denied.
9. Restart the stack and replay the packaged video:

```bash
sudo docker compose --env-file .env restart
sudo docker compose --env-file .env ps
```

For existing videos added after launch, preview and batch the backfill:

```bash
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" transcode-lesson-videos --dry-run
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" transcode-lesson-videos --limit 10
```

## 7. Encrypted off-host backups

Mount the remote filesystem at the `BACKUP_MOUNT` in `.env`. NFS, a storage appliance mount, or another already-secured remote filesystem is acceptable. Configure it in `/etc/fstab` so it is available after reboot.

The backup script refuses to run unless `BACKUP_MOUNT` is an active mount point; it will not silently fill a local directory when the remote target is offline.

The backup container runs as UID/GID 1000. Prepare its repository directory accordingly:

```bash
sudo install -d -o 1000 -g 1000 -m 0700 /mnt/rmu-lms-backups/restic
mountpoint /mnt/rmu-lms-backups
```

Adjust the path if `.env` uses a different mount.

Run and inspect the first backup manually:

```bash
cd /opt/rmu-lms/deployment
sudo ./scripts/backup-host.sh
sudo docker compose --env-file .env --profile backup run --rm \
  --entrypoint restic backup snapshots
```

Each run:

- creates a logical MariaDB dump and Frappe configuration backup;
- snapshots `site_config.json`, public files, private files, uploaded audio sources, and completed DASH packages;
- excludes logs, indexes, locks, existing local backups, and `videos/.tmp` staging trees;
- checks repository metadata; and
- retains 7 daily, 4 weekly, and 6 monthly snapshots before pruning.

Install the systemd timer. These supplied units assume the repository is `/opt/rmu-lms`; edit both paths first if it is elsewhere.

```bash
sudo install -m 0644 systemd/rmu-lms-backup.service /etc/systemd/system/
sudo install -m 0644 systemd/rmu-lms-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rmu-lms-backup.timer
sudo systemctl list-timers rmu-lms-backup.timer
```

Inspect results and failures:

```bash
sudo systemctl start rmu-lms-backup.service
sudo systemctl status rmu-lms-backup.service
sudo journalctl -u rmu-lms-backup.service --since today
```

Back up `/etc/rmu-lms/restic-password` separately in an approved secret manager. Do not store it inside the Restic repository.

## 8. Quarterly restore drill

Run recovery tests in an isolated Compose project or another server. Never test by overwriting production.

1. Copy `deployment/` to the recovery host and use the same application digest as the snapshot tag.
2. Set a distinct project name and port:

   ```bash
   export COMPOSE_PROJECT_NAME=rmu-lms-restore
   sed -i 's/^FRONTEND_BIND=.*/FRONTEND_BIND=127.0.0.1:18080/' .env
   ```

3. Restore the latest Restic snapshot to a host staging directory:

   ```bash
   sudo install -d -m 0700 /srv/rmu-lms-restore
   sudo docker compose --env-file .env --profile backup run --rm \
     --volume /srv/rmu-lms-restore:/restore \
     --entrypoint restic backup restore latest --target /restore
   ```

4. Start the isolated database, Redis, configurator, and backend. Create a blank site with the original `SITE_NAME`, install Payments/LMS, and stop application workers before restoring.
5. Locate the restored `.sql.gz` file below `/srv/rmu-lms-restore`, then restore it interactively:

   ```bash
   sudo docker compose --env-file .env exec backend \
     bench --site "$SITE_NAME" restore /path/inside/container/database.sql.gz
   ```

   Copy the dump into the backend first with `docker compose cp` if necessary.

6. Copy the restored `public/files` and `private/files` trees into the isolated site's volume. Run a one-shot container as root to reset ownership to `1000:1000`.
7. Read `encryption_key` from the restored `site_config.json` and apply only that key to the newly created site's config. Preserve the recovery site's freshly generated `db_name` and `db_password`; do not replace its whole config with production database credentials.
8. Run `bench --site "$SITE_NAME" migrate`, start the isolated stack, and test it through port 18080 with the original Host header.

A recovery drill passes only when an administrator can sign in, the expected apps and records exist, and a private multi-audio DASH video plays. Perform this drill at least quarterly and after material storage or database changes.

## 9. Release deployment

Frappe migrations are not assumed reversible. Always back up before changing the image.

Record the currently deployed digest:

```bash
grep '^LMS_IMAGE=' .env
```

Create and verify a backup **before editing `.env`**:

```bash
sudo ./scripts/backup-host.sh
sudo docker compose --env-file .env --profile backup run --rm \
  --entrypoint restic backup snapshots --latest 1
```

Update `LMS_IMAGE` to the new release digest, then pull it:

```bash
editor .env
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env pull
```

Enter maintenance mode, stop request/background processes, and leave MariaDB/Redis running:

```bash
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" set-maintenance-mode on
sudo docker compose --env-file .env stop frontend queue-short queue-long scheduler websocket backend
sudo docker compose --env-file .env up -d db redis-cache redis-queue configurator
```

Run the migration exactly once with the new image. Do not use `--skip-failing`.

```bash
sudo docker compose --env-file .env run --rm backend \
  bench --site "$SITE_NAME" migrate
```

Start and verify the complete stack:

```bash
sudo docker compose --env-file .env up -d
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" set-maintenance-mode off
sudo docker compose --env-file .env exec backend \
  bench --site "$SITE_NAME" check-video-pipeline
sudo docker compose --env-file .env ps
curl --fail "https://$SITE_NAME/api/method/ping"
```

### Rollback

- If migration has **not** run, put the previous digest back in `.env`, pull, and run `docker compose up -d`.
- If migration started or failed, do not merely start the old image. Restore the pre-deploy database/configuration/files snapshot into an isolated environment, verify it, then restore production and return to the prior image digest during a declared maintenance window.

Database/file restoration is intentionally manual because it is destructive and must identify an exact validated snapshot first.

## 10. Routine operations

```bash
# Status and resource usage
sudo docker compose --env-file .env ps
docker stats

# Logs
sudo docker compose --env-file .env logs --tail=200 backend
sudo docker compose --env-file .env logs --tail=200 queue-long
sudo docker compose --env-file .env logs --tail=200 scheduler

# Frappe shell and maintenance
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" console
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" clear-cache
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" doctor

# Pipeline health
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" check-video-pipeline

# Queued jobs and failed jobs
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" show-pending-jobs

# Disk and volume inventory
df -h
docker system df
docker volume ls
```

Alert at 70% disk use and treat 85% as critical. Never prune Docker volumes as a cleanup shortcut. Remove old images only after confirming they are not the active or rollback digest.

## 11. Troubleshooting

### GHCR returns `denied` or `unauthorized`

- Confirm the token is classic and includes `read:packages`.
- Authorize organization SSO.
- Confirm the package grants the machine user access.
- Run `docker logout ghcr.io`, authenticate again, then pull the exact digest.

### Frappe reports that the host does not exist

- `SITE_NAME` must be the site directory name and public DNS name.
- Apache must preserve `Host`.
- The frontend service must receive the same `FRAPPE_SITE_NAME_HEADER`.
- Test the inner proxy with `curl -H "Host: $SITE_NAME" http://127.0.0.1:8080`.

### WebSockets do not connect

- Confirm `proxy`, `proxy_http`, and `headers` modules are enabled.
- Confirm Apache is 2.4.47 or newer.
- Inspect `websocket`, `frontend`, and Apache SSL logs.
- Ensure `/socket.io/` appears before `/` in the Apache configuration.

### Upload returns HTTP 413

The two application limits must agree; Apache must not impose a smaller ceiling:

- Apache `LimitRequestBody 0` (unlimited at this layer).
- Compose `CLIENT_MAX_BODY_SIZE=2g`.
- Frappe site config `max_file_size=2147483648`.

Reload Apache and recreate the frontend after changes.

### Assets are missing after an image update

```bash
sudo docker compose --env-file .env restart frontend backend
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" clear-cache
```

The image entrypoint replaces `sites/assets` with a symlink to the baked image assets each time a container starts.

### Video packaging fails

```bash
sudo docker compose --env-file .env exec backend bench --site "$SITE_NAME" check-video-pipeline
sudo docker compose --env-file .env exec queue-long ffmpeg -version
sudo docker compose --env-file .env exec queue-long ffprobe -version
sudo docker compose --env-file .env exec queue-long packager --version
sudo docker compose --env-file .env logs --tail=500 queue-long
```

Confirm LMS Settings uses **Binary**, not Docker, and that no custom Packager path points elsewhere.

### Jobs are queued but never run

Check `queue-short`, `queue-long`, Redis queue health, and scheduler logs. Recreate only the failed stateless process:

```bash
sudo docker compose --env-file .env up -d --force-recreate queue-long
```

### Stale video staging directories consume disk

The daily LMS maintenance job sweeps stale packaging work. First confirm no media job is running, inspect `LMS Video`/worker logs, and allow the scheduler to perform cleanup. Do not delete `manifest.mpd`, `video/`, or `audio_*` folders from ready packages.

### Backup fails immediately

Run `mountpoint "$BACKUP_MOUNT"`, inspect permissions as UID 1000, verify the Restic password file, and read `journalctl -u rmu-lms-backup.service`. The mount-point failure is intentional protection against writing backups onto the application disk.

## Source references

- [Frappe production setup](https://docs.frappe.io/framework/user/en/bench/guides/setup-production)
- [Frappe v15 prerequisites](https://docs.frappe.io/framework/user/en/installation)
- [Official Frappe Docker deployment methods](https://github.com/frappe/frappe_docker/blob/main/docs/01-getting-started/01-choosing-a-deployment-method.md)
- [Frappe Docker custom image setup](https://github.com/frappe/frappe_docker/blob/main/docs/02-setup/02-build-setup.md)
- [Frappe backup command](https://docs.frappe.io/framework/user/en/bench/reference/backup)
- [Frappe migrate command](https://docs.frappe.io/framework/user/en/bench/reference/migrate)
- [GitHub Container Registry authentication](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Apache reverse proxy and WebSocket upgrades](https://httpd.apache.org/docs/2.4/mod/mod_proxy.html)
- [Certbot Apache instructions](https://certbot.eff.org/instructions?os=snap&ws=apache)
