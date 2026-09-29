# RMU Somalia LMS: deploy from source with Docker

This deployment builds the application's Docker image on the server. There is
no GitHub Release, GHCR login, image push, or image digest to copy. The image
contains Frappe, Payments, LMS, the built Shaka Player frontend, ffmpeg,
ffprobe, and the checksum-verified Shaka Packager binary. Compose runs that
same image for the web processes, workers, scheduler, and backups; it also runs
pinned MariaDB and Redis images.

The deployment is independent of `apps/lms/deploy/`. Do not mix commands or
volumes from that directory into this stack.

## One-time host preparation

Production hosts are Ubuntu 24.04 or RHEL, with Docker Engine and
Compose (`docker compose` or `docker-compose`), systemd, sudo access, and Apache
HTTPS for the LMS subdomain. The existing capacity recommendation is at least 16 vCPU, 32 GB
RAM, and 1 TB NVMe storage. Keep enough free space for source videos, packaged
media, local snapshots, and the Docker build cache. Compose caps each
container's CPU through the `*_CPUS` values in `deployment/.env`; lower them on
a small host and raise them on a larger one. No value may exceed the CPU count
available to the Docker engine (for example, `QUEUE_LONG_CPUS=4.0` on a 4-CPU
host), or Compose refuses to create that container. On SELinux-enforcing RHEL,
the script labels only its two secret files for container access; Compose
labels the dedicated backup mount for sharing between backup containers.

For a full local deployment on macOS, use Docker Desktop with Compose and run
the script as your normal user, not with `sudo`. The application image is
`linux/amd64` because it contains pinned x64 binaries. ARM hosts, including
Apple Silicon, need Docker's amd64 emulation; the first build and video
processing can be slow. No Apache or TLS is needed for this local setup. Keep
Docker Desktop running for scheduled backups.

The server needs access to:

- the Git repository when you choose to pull source updates;
- Docker Hub for the pinned Python, MariaDB, and Redis base images; and
- Debian, PyPI, Yarn/npm, nodejs.org, and GitHub for the build dependencies.

The build verifies downloaded Node.js, wkhtmltopdf, and Shaka Packager files
with the SHA-256 values in `Containerfile`. Docker caches build layers, so
unchanged dependencies normally do not download again.

Clone the repository as the user who will run deployments. On Linux, for example:

```bash
sudo install -d -o "$USER" -g "$(id -gn)" /opt/rmu-lms
git clone https://github.com/ballgam/frappe-rmu-lms.git /opt/rmu-lms
cd /opt/rmu-lms
docker version
docker compose version
```

On macOS, clone it under a Docker Desktop-shared directory such as your home
directory, then confirm `docker info` and either `docker compose version` or
`docker-compose version` work.

For a private repository, configure that user's Git authentication before
choosing to pull updates. The server checkout's tracked upstream branch is the
source of updates; its remote does not have to be named `origin`.

For production, ask the Apache administrator to route the LMS HTTPS hostname to
`127.0.0.1:8080` (or the local port selected at the first prompt). The proxy
must preserve `Host`, forward `X-Forwarded-Proto: https`, pass WebSocket
upgrades for `/socket.io/`, and allow the intended 2 GB upload size with a
660-second timeout. The supplied [Apache HTTPS template](apache/rmu-lms-ssl.conf.example)
shows those settings. The deployment script does not change Apache or request
certificates.

## Deploy or update

Run this command from the checkout as its owner, **without** `sudo`:

```bash
./deployment/deploy.sh
```

On each normal run, press Enter (or `y`) to fetch and fast-forward the tracked
upstream branch, or enter `n` to build the commit already checked out on the
server without contacting the Git remote. Either choice requires a clean
checkout; commit local edits before deploying. If an upgrade is pending, the
script resumes that revision without asking or fetching new source.

On the first run, choose an Administrator password and accept local port `8080`
unless it is occupied. On Linux, enter the public LMS hostname (without
`https://`); the script asks for sudo when it needs Docker or root-owned files.
It creates `deployment/.env`, two root-only secrets under `/etc/rmu-lms/`, and
encrypted local backups under `/var/backups/rmu-lms/`. On macOS, accept the
default `lms.localhost` hostname. The script creates user-owned secrets and
encrypted backups under ignored `deployment/local-data/` and serves the site
at `http://127.0.0.1:8080/lms` (or your chosen local port). Do not delete
that directory if you want to retain its backup snapshots.

On later runs, the same command:

1. Refuses local source edits, then either fast-forwards from the branch's
   configured upstream or uses the current checked-out commit. A pull also
   refuses a diverged branch.
2. Builds and checks one local image tagged with the full source commit SHA.
3. Takes and verifies an encrypted backup before starting a migration.
4. Enters maintenance mode, migrates once, restarts the stack, and checks the
   site and video tools.

The build runs while the old application is still serving requests. A failed
build therefore leaves the current site in place. The script records pending
upgrade phases in `deployment/.deploy-pending`; an interrupted run resumes a
safe phase. If migration started but did not finish, it stops and asks for
manual recovery because reversing Frappe migrations automatically is unsafe.
Do not delete the pending file as a shortcut.

If this server already runs the former GHCR deployment, keep its `.env`, Docker
volumes, and current image. The first local-build run uses that image for the
pre-upgrade backup, then switches to the newly built local image. It does not
remove the old image or any data volumes.

If an upgrade has stopped before migration begins and you need to return to
the previous image, run `./deployment/deploy.sh --abort-pending`. The command
refuses to roll back once migration may have started.

On Linux, the script reports whether the public HTTPS check passed. A local
health check can pass before the Apache route is configured; in that case it
prints the local address and the remaining proxy action. On macOS, it reports
the local HTTP address and does not require a public HTTPS route.

## What runs

The site is hosted by one Compose project named `rmu-lms`:

```text
Apache HTTPS (production; managed by the server administrator)
    -> 127.0.0.1:8080 -> frontend Nginx -> Frappe backend
                                      -> Socket.IO
Docker-only network -> short/default worker, long worker pool, scheduler
                    -> MariaDB 10.11, Redis cache, persistent Redis queue
```

The long worker runs ffmpeg, ffprobe, and `/usr/local/bin/packager` in Binary
mode. No Docker socket is mounted in the application containers. Video source
and DASH output share the persistent POSIX `sites` volume; this matters for
file locks and atomic `manifest.mpd` updates. The upload limit is 2 GB, and the
default two Gunicorn workers limit simultaneous upload memory spikes.

The image build and runtime checks include `ffmpeg`, `ffprobe`, Packager,
Shaka Player assets, and `bench --site ... check-video-pipeline`. Before opening
enrollment, upload a short recording and confirm that an `LMS Video` reaches
**Ready** and plays with its audio tracks.

## Local backups and recovery

`deployment/scripts/backup-host.sh` creates encrypted Restic snapshots in
`/var/backups/rmu-lms/restic` on Linux or `deployment/local-data/backups/restic`
on macOS. Linux uses the existing systemd timer for nightly backups; macOS
starts a backup-scheduler container that repeats a backup every 24 hours while
Docker Desktop is running. A snapshot contains a logical database dump, site
configuration, public/private files,
and completed DASH packages. It excludes transient media staging files. The
backup script checks repository metadata and retains 7 daily, 4 weekly, and
6 monthly snapshots, plus the three most recent snapshots so a deployment
backup is not immediately displaced by the nightly timer.

Inspect snapshots from `deployment/` (omit `sudo` on macOS):

```bash
sudo ./scripts/compose-cli.sh --env-file .env --profile backup run --rm \
  --entrypoint restic backup snapshots
```

Keep `/etc/rmu-lms/restic-password` on Linux, or
`deployment/local-data/secrets/restic-password` on macOS, in a separate secure
location. Without it, the snapshots cannot be read. Local backups protect
against a bad deployment but not against host or disk loss. Arrange a separate
copy of the backup directory before relying on it for disaster recovery.

If a migration is interrupted, leave the old image available and inspect
`deployment/.deploy-pending` plus the backend logs. Do not start the old image
against a database that the new image may have migrated. Select the exact
pre-upgrade snapshot, restore and test it in an isolated Compose project, then
plan the production restore. Restoring the database or site files in production
overwrites live state, so the script does not do this automatically. The
previous image tag and source SHA remain recorded for that recovery work.

## Status and troubleshooting

From `deployment/` (omit `sudo` on macOS):

```bash
sudo ./scripts/compose-cli.sh --env-file .env ps
sudo ./scripts/compose-cli.sh --env-file .env logs --tail=200 backend
sudo ./scripts/compose-cli.sh --env-file .env logs --tail=200 queue-long
sudo ./scripts/compose-cli.sh --env-file .env exec backend \
  bench --site YOUR_LMS_DOMAIN check-video-pipeline
curl --fail --header 'Host: YOUR_LMS_DOMAIN' \
  http://127.0.0.1:8080/api/method/ping
```

If the inner URL works but HTTPS does not, check the Apache route, certificate,
forwarded host/protocol headers, and WebSocket proxy. If video packaging fails,
inspect the long worker and run `ffmpeg -version`, `ffprobe -version`, and
`packager --version` inside it. Never prune Docker volumes as a cleanup step:
they contain the site, database, and persistent queue.

## Remove the deployment completely

There is no uninstall command in `deploy.sh`. Removal is a deliberate sequence.
It deletes the site, database, persistent queue, secrets, and every local backup
snapshot. These steps are not reversible.

`deployment/destroy.sh` automates steps 2 through 5 below (and the Apache
cleanup in step 6 with `--remove-apache`); the manual commands are documented so
you can run or audit them yourself.

```bash
./deployment/destroy.sh                     # prompts, then removes the stack
./deployment/destroy.sh --yes                # skip the typed confirmation
./deployment/destroy.sh --remove-apache      # also remove the vhost and cert
```

Do them in order. `docker compose down` reads `deployment/.env` and the secret
files, so remove those only after the stack is gone.

### 1. Preserve anything you still need

If any data must survive, copy a snapshot and the Restic password off this host
now; once the backup directory is deleted the snapshots cannot be recovered.

```bash
# Linux
sudo cp -a /var/backups/rmu-lms /media/offsite/rmu-lms-backups
sudo cp -a /etc/rmu-lms/restic-password /media/offsite/rmu-lms-restic-password

# macOS
cp -a deployment/local-data/backups /Volumes/offsite/rmu-lms-backups
cp -a deployment/local-data/secrets/restic-password /Volumes/offsite/rmu-lms-restic-password
```

Confirm the copy is readable before continuing. Also note the public hostname
and the deployed image for the record.

### 2. Stop and delete the stack and volumes

Run from `deployment/`. Include both profiles so the `backup` and
`backup-scheduler` containers are removed too (omit `sudo` on macOS):

```bash
sudo ./scripts/compose-cli.sh --env-file .env \
  --profile backup --profile backup-scheduler down \
  --volumes --remove-orphans
```

`--volumes` deletes the named volumes `rmu-lms_sites`, `rmu-lms_db-data`, and
`rmu-lms_redis-queue-data`, which hold all site files, the database, and the
persistent queue. Verify nothing remains:

```bash
docker volume ls | grep rmu-lms        # expect no output
docker ps -a --filter name=rmu-lms     # expect no output
```

### 3. Remove the local images

```bash
docker rmi $(docker images --filter reference='rmu-lms*' -q) 2>/dev/null || true
docker images | grep -E 'rmu-lms|ghcr.io'   # remove any former GHCR image shown
```

### 4. Remove the backup timer and units

```bash
sudo systemctl disable --now rmu-lms-backup.timer 2>/dev/null || true
sudo rm -f /etc/systemd/system/rmu-lms-backup.service \
           /etc/systemd/system/rmu-lms-backup.timer
sudo systemctl daemon-reload
sudo systemctl reset-failed 2>/dev/null || true
```

### 5. Remove secrets, backups, and deployment state

```bash
# Linux
sudo rm -rf /etc/rmu-lms
sudo rm -rf /var/backups/rmu-lms

# macOS
rm -rf deployment/local-data

# Both platforms
rm -f deployment/.env deployment/.deploy-pending
```

### 6. Remove the Apache route and certificate

Use the reverse of [apache/README.md](apache/README.md). Disable the vhost and
revoke or delete the certificate:

```bash
# Ubuntu
sudo a2dissite rmu-lms && sudo rm -f /etc/apache2/sites-available/rmu-lms.conf
sudo certbot delete --cert-name LMS_DOMAIN
sudo apachectl configtest && sudo systemctl reload apache2

# RHEL
sudo rm -f /etc/httpd/conf.d/rmu-lms.conf
sudo certbot delete --cert-name LMS_DOMAIN
sudo apachectl configtest && sudo systemctl reload httpd
```

Remove the public DNS record for `LMS_DOMAIN` and close ports 80/443 in the
firewall if this host no longer serves anything.

### 7. Remove the source checkout

```bash
sudo rm -rf /opt/rmu-lms
```

After this the host holds no RMU LMS data, images, containers, secrets, or
configuration. Removing Docker Engine itself is out of scope and optional.
