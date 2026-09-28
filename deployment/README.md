# RMU Somalia LMS: deploy from source on one Ubuntu server

This deployment builds the application's Docker image on the server. There is
no GitHub Release, GHCR login, image push, or image digest to copy. The image
contains Frappe, Payments, LMS, the built Shaka Player frontend, ffmpeg,
ffprobe, and the checksum-verified Shaka Packager binary. Compose runs that
same image for the web processes, workers, scheduler, and backups; it also runs
pinned MariaDB and Redis images.

The deployment is independent of `apps/lms/deploy/`. Do not mix commands or
volumes from that directory into this stack.

## One-time server preparation

Use an Ubuntu 24.04 x86_64 server with Docker Engine and its Compose plugin,
Apache with HTTPS for the LMS subdomain, and sudo access. The existing capacity
recommendation is at least 16 vCPU, 32 GB RAM, and 1 TB NVMe storage. Keep
enough free space for source videos, packaged media, local snapshots, and the
Docker build cache.

The server needs access to:

- the Git repository from which it will fetch source updates;
- Docker Hub for the pinned Python, MariaDB, and Redis base images; and
- Debian, PyPI, Yarn/npm, nodejs.org, and GitHub for the build dependencies.

The build verifies downloaded Node.js, wkhtmltopdf, and Shaka Packager files
with the SHA-256 values in `Containerfile`. Docker caches build layers, so
unchanged dependencies normally do not download again.

Clone the repository as the user who will run deployments. For example:

```bash
sudo install -d -o "$USER" -g "$(id -gn)" /opt/rmu-lms
git clone https://github.com/ballgam/frappe-rmu-lms.git /opt/rmu-lms
cd /opt/rmu-lms
docker version
docker compose version
```

For a private repository, configure that user's Git authentication first. The
server checkout's tracked upstream branch is the source of updates; its remote
does not have to be named `origin`.

Ask the Apache administrator to route the LMS HTTPS hostname to
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

On the first run, enter the public LMS hostname (without `https://`), accept
local port `8080` unless it is occupied, and choose an Administrator password.
The script asks for sudo when it needs Docker or root-owned files. It creates
`deployment/.env`, two root-only secrets under `/etc/rmu-lms/`, and an encrypted
local backup repository under `/var/backups/rmu-lms/`.

On later runs, the same command:

1. Refuses local source edits or a diverged branch, then fast-forwards from the
   branch's configured upstream.
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

The script reports whether the public HTTPS check passed. A local health check
can pass before the Apache route is configured; in that case it prints the
local address and the remaining proxy action.

## What runs

The site is hosted by one Compose project named `rmu-lms`:

```text
Apache HTTPS (managed by the server administrator)
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
`/var/backups/rmu-lms/restic`. A systemd timer also runs it nightly. A snapshot
contains a logical database dump, site configuration, public/private files,
and completed DASH packages. It excludes transient media staging files. The
backup script checks repository metadata and retains 7 daily, 4 weekly, and
6 monthly snapshots, plus the three most recent snapshots so a deployment
backup is not immediately displaced by the nightly timer.

Inspect snapshots from `deployment/`:

```bash
sudo docker compose --env-file .env --profile backup run --rm \
  --entrypoint restic backup snapshots
```

Keep `/etc/rmu-lms/restic-password` in a separate secure location. Without it,
the snapshots cannot be read. Backups on this server protect against a bad
deployment but not against server or disk loss. Arrange a separate copy of the
backup directory before relying on it for disaster recovery.

If a migration is interrupted, leave the old image available and inspect
`deployment/.deploy-pending` plus the backend logs. Do not start the old image
against a database that the new image may have migrated. Select the exact
pre-upgrade snapshot, restore and test it in an isolated Compose project, then
plan the production restore. Restoring the database or site files in production
overwrites live state, so the script does not do this automatically. The
previous image tag and source SHA remain recorded for that recovery work.

## Status and troubleshooting

From `deployment/`:

```bash
sudo docker compose --env-file .env ps
sudo docker compose --env-file .env logs --tail=200 backend
sudo docker compose --env-file .env logs --tail=200 queue-long
sudo docker compose --env-file .env exec backend \
  bench --site YOUR_LMS_DOMAIN check-video-pipeline
curl --fail --header 'Host: YOUR_LMS_DOMAIN' \
  http://127.0.0.1:8080/api/method/ping
```

If the inner URL works but HTTPS does not, check the Apache route, certificate,
forwarded host/protocol headers, and WebSocket proxy. If video packaging fails,
inspect the long worker and run `ffmpeg -version`, `ffprobe -version`, and
`packager --version` inside it. Never prune Docker volumes as a cleanup step:
they contain the site, database, and persistent queue.
