# Deploying this LMS publicly

Production deployment on a single VPS via [frappe_docker](https://github.com/frappe/frappe_docker),
sized for a pilot cohort under 200 learners.

For local development use `docker/docker-compose.yml` instead — that stack is not
what this directory is about.

## Why not a managed platform

The video pipeline in [`lms/lms/video/`](../lms/lms/video/README.md) shells out to two external
tools. `ffmpeg` is an apt package and is easy anywhere. Shaka Packager is not: it ships no OS
package, so `pipeline.py` defaults to running `docker run google/shaka-packager`, which needs a
mounted `/var/run/docker.sock` inside the container. No managed platform grants that, and it is
not something to give a public web container in any case.

The way out is already in the code. `PACKAGER_BINARY_NAMES` in `pipeline.py` accepts a plain
binary, and LMS Settings has a `Binary` packager mode. `Dockerfile.media` installs the static
binary and Phase 3 flips the switch, so Docker leaves the request path entirely.

Frappe Cloud remains possible if you ever want it — `pyproject.toml` already declares `ffmpeg`
under `[deploy.dependencies.apt]`, which Frappe Cloud honours — but Shaka would have to be
vendored into this repo, and sustained transcoding needs a Dedicated Server plan.

## Architecture

| Service | Role | Notes |
|---|---|---|
| `traefik` | TLS, Let's Encrypt | `overrides/compose.https.yaml` |
| `frontend` | nginx; assets, and X-Accel for private files | `CLIENT_MAX_BODY_SIZE` must be raised |
| `backend` | gunicorn | needs `ffprobe`: the settings preflight runs in a web request |
| `websocket` | socket.io | live encode-progress events |
| `queue-long` + `queue-video` | RQ workers | where ffmpeg and packager actually run |
| `queue-short`, `scheduler` | routine jobs | `video/maintenance.py` re-enqueues stranded track jobs |
| `db`, `redis-cache`, `redis-queue` | `compose.mariadb.yaml`, `compose.redis.yaml` | |
| volume `sites` | `sites/<site>/private/files/videos/<video_id>/` | the thing to back up |

Host: 4 vCPU / 8–16 GB RAM / ≥200 GB disk. A packaged video is several times the size of its
source, and `keep_original_video` defaults to on, which keeps both.

---

## Phase 0 — prerequisites

**This repo must be standalone.** If you are reading this inside the `frappe-bench` monorepo,
the split has not happened yet. `apps/frappe`, `apps/lms` and `apps/payments` have no `.git` of
their own there; everything is vendored into one repo, and no Frappe deployment tool can consume
that shape.

`git subtree split` only sees committed history, so **commit this `deploy/` directory and the
`pyproject.toml` change first**, otherwise they will not be in the split.

```bash
# from the bench repo, preserving history
git add apps/lms/deploy apps/lms/pyproject.toml
git commit -m "deploy: production hosting setup"

git subtree split -P apps/lms -b lms-only
git push git@github.com:RMU-Somalia/lms.git lms-only:main
```

The split has been rehearsed: it produces a tree with `pyproject.toml` at the root, 1,296 files,
and no `sites/` or `apps/` paths.

`apps/frappe` and `apps/payments` are unmodified upstream (one commit each, the initial import),
so nothing needs to be split out of them — `apps.json` points at upstream.

Minor cleanup while you are in there: `.gitmodules` still declares a `frappe-ui` submodule, but
there is no gitlink in the index and `frappe-ui/` on disk is empty. The frontend takes `frappe-ui`
from npm (`^1.0.0-beta.24` in `frontend/package.json`), so the declaration is inert and does not
affect the build — it is just misleading.

> **Do not reuse dev credentials.** `sites/learning.test/site_config.json` was committed in the
> bench repo's initial commit and removed later, so its `db_password` and `encryption_key` are
> still in that history. They are local-dev values; generate fresh ones for production. The split
> repo contains no `sites/` directory, so the exposure stays confined to the bench repo.

## Phase 1 — build the image

Two layers: upstream builds the bench, `Dockerfile.media` adds the media tools. Keeping them
separate means `git pull` in frappe_docker and a rebuild, with no patch to re-apply.

```bash
git clone https://github.com/frappe/frappe_docker
cd frappe_docker

cp /path/to/lms/deploy/apps.json.example apps.json   # edit if the repo is private
export APPS_JSON_BASE64=$(base64 -w 0 apps.json)

docker build \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg=FRAPPE_BRANCH=version-15 \
  --build-arg=APPS_JSON_BASE64=$APPS_JSON_BASE64 \
  --tag=ghcr.io/rmu-somalia/lms-base:v1 \
  --file=images/custom/Containerfile .
```

If `RMU-Somalia/lms` is private, do **not** put a PAT in `--build-arg`. Build args are recorded
in image layer metadata and are trivially extractable
([frappe_docker#1860](https://github.com/frappe/frappe_docker/issues/1860)). Use the BuildKit
secret form instead:

```bash
DOCKER_BUILDKIT=1 docker build --secret id=apps_json,src=apps.json ...
```

Then the media layer:

```bash
cd /path/to/lms
docker build -t ghcr.io/rmu-somalia/lms:v1 \
  --build-arg BASE_IMAGE=ghcr.io/rmu-somalia/lms-base:v1 \
  -f deploy/Dockerfile.media deploy/
docker push ghcr.io/rmu-somalia/lms:v1
```

Notes:

- Every service in frappe_docker's `compose.yaml` pins `platform: linux/amd64`. Build amd64
  unless you also override that; `Dockerfile.media` handles arm64 if you do.
- The frontend build (Vite, inside `bench build`) is memory-hungry. If it OOMs, give the builder
  more memory or pass `NODE_OPTIONS=--max-old-space-size=4096`.
- The packager binary is pinned by SHA256 per architecture in `Dockerfile.media`. Bump the
  version and both hashes together.

## Phase 2 — deploy

```bash
cp /path/to/lms/deploy/env.example .env      # then fill in the marked values
cp /path/to/lms/deploy/compose.video-worker.yaml overrides/

docker compose -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml \
  -f overrides/compose.https.yaml \
  -f overrides/compose.video-worker.yaml \
  config > ~/gitops/lms.yml

docker compose --project-name lms -f ~/gitops/lms.yml up -d
```

DNS must already point at the server or Let's Encrypt validation fails.

Create the site:

```bash
docker compose --project-name lms -f ~/gitops/lms.yml exec backend \
  bench new-site learning.example.edu \
    --install-app lms \
    --admin-password '<generate one>' \
    --mariadb-root-password "$DB_PASSWORD" \
    --set-default
```

`payments` installs as a dependency — `pyproject.toml` declares it under
`[tool.bench.frappe-dependencies]`.

## Phase 3 — configure video

```bash
docker compose --project-name lms -f ~/gitops/lms.yml exec backend \
  bench --site learning.example.edu set-config max_file_size 2147483648
```

Then in the desk UI, **LMS Settings → Video Processing**:

| Field | Value |
|---|---|
| Shaka Packager Mode | **Binary** |
| Shaka Packager Path | `/usr/local/bin/packager` |
| Docker Path | *(empty)* |
| ffmpeg Path / ffprobe Path | *(empty — both on PATH)* |
| Video Transcoding Enabled | on |
| Segment Duration | 4 |
| Token TTL (hours) | 12 |

Saving re-runs the preflight in `pipeline.py`, which rejects an unexecutable path — so a
successful save is real evidence, not just a stored string.

## Phase 4 — backups

`bench backup --with-files` tars `private/files`, which with video packages is unusable. Split it:

- **Database and non-video files** — nightly `bench backup`, pushed off-box with restic or rclone.
- **Video packages** — a separate, less frequent `rclone sync` of
  `sites/<site>/private/files/videos/`. Packages are immutable once written, so every sync after
  the first is cheap.
- Rehearse a restore into a throwaway compose project *before* the pilot opens.

---

## Verification

Each step gates the next.

1. **Tools present**
   ```bash
   docker compose --project-name lms -f ~/gitops/lms.yml exec queue-video \
     bash -lc 'ffmpeg -version | head -1; packager --version'
   ```
2. **Preflight** — must report ffmpeg, ffprobe and packager resolved in `Binary` mode, with no
   mention of Docker:
   ```bash
   docker compose --project-name lms -f ~/gitops/lms.yml exec backend \
     bench --site learning.example.edu check-video-pipeline
   ```
3. **HTTPS** — `curl -I https://learning.example.edu` returns 200 with a valid Let's Encrypt chain.
4. **End-to-end upload** — as a Course Creator, upload a multi-track lecture into a lesson. Watch
   `docker compose logs -f queue-video`; the `LMS Video` doc should move Queued → Processing →
   Ready, and `private/files/videos/<id>/` should hold `manifest.mpd`, `video/`, and one
   `audio_<lang>/` per track.
5. **Playback** — as an enrolled learner, the Shaka audio menu lists every track, and switching
   does not restart the video.
6. **X-Accel engaged** — a request to `.../serve_video_segment` returns bytes with
   `Accept-Ranges: bytes`, and the `frontend` access log shows the `/protected/` internal
   redirect. Without this every segment streams through gunicorn.
7. **Add a track post-publish** — lesson editor → Audio Tracks → Add an audio track. Should
   finish in about a minute even for a long lecture, and must not rewrite `video/`.
8. **Access control** — log out, request a segment URL directly, expect a permission error from
   `_verify_token`.
9. **Large upload** — a file near the 2 GB ceiling completes with no 413 and no 504.
10. **Existing content** — pre-packaging videos still play as progressive files. Backfill when
    ready: `bench --site ... transcode-lesson-videos --dry-run`, then `--limit 10`.

## Known limitations

Acceptable at pilot scale; these are the seams that fail first.

- **Uploads are buffered in RAM.** Frappe's `upload_file` holds the whole file. Two concurrent
  2 GB uploads on an 8 GB box will OOM it. Chunked/resumable upload is the real fix — the video
  README already names it as the obvious follow-up.
- **Every segment costs a Python request.** Even with X-Accel doing the byte-pushing, routing and
  the `LMS Video` row lookup happen in gunicorn per segment. At institution scale this wants
  object storage plus a CDN with signed URLs rather than the token endpoint.
- **`queue-video` is a second consumer, not an isolated queue.** Both video jobs hard-code
  `queue="long"`. Real isolation needs a code change.
- **Image builds are manual.** Worth a GitHub Actions workflow building and pushing on tag before
  the second deploy.
