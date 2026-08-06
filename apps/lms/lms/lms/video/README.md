# Multi-audio-track video

Instructors upload lecture recordings that carry several translated audio tracks
(English + Somali narration of the same lecture, say). A browser only ever
decodes the *first* audio track of a plain `<video>` source, so those extra
tracks were dead weight in the file and learners had no way to reach them.

Uploads are therefore repackaged as MPEG-DASH with one AdaptationSet per audio
track, and played with [Shaka Player](https://github.com/shaka-project/shaka-player),
which exposes an audio menu.

```
upload → ffprobe → ffmpeg (normalize, one output per stream) → shaka-packager → manifest.mpd
```

## Setup

**1. ffmpeg and ffprobe** must be on the bench's PATH (or set explicitly in
LMS Settings → Video Processing).

```bash
apt install ffmpeg          # Debian/Ubuntu
brew install ffmpeg         # macOS
```

**2. Shaka Packager.** It ships no OS packages, so the default is to run the
official image — nothing to install on the bench beyond Docker:

```bash
docker pull google/shaka-packager
```

If your deployment image already bundles the binary, switch
LMS Settings → Video Processing → *Shaka Packager Mode* to `Binary`.

**3. Verify** before relying on it:

```bash
bench --site <site> check-video-pipeline
```

**4. Raise the upload limit.** `max_file_size` defaults to 25 MB, which no real
lecture fits under:

```bash
bench --site <site> set-config max_file_size 2147483648   # 2 GB
```

and in nginx, `client_max_body_size 2g;`.

> Uploads are buffered fully in memory by Frappe's `upload_file`, so a 2 GB
> upload is a 2 GB spike in the web worker. Chunked/resumable upload is the
> obvious follow-up; until then size the limit to what your workers can hold.

**5. Give packaging its own worker** if you can. A 40-minute lecture occupies
the `long` queue for minutes, and that queue also carries course-progress
recalculation and course import/export.

## Backfilling existing videos

Videos uploaded before this feature keep playing as ordinary progressive files —
nothing breaks, they just have no audio menu. Package them in batches when you
choose:

```bash
bench --site <site> transcode-lesson-videos --dry-run
bench --site <site> transcode-lesson-videos --limit 10
bench --site <site> transcode-lesson-videos --retry-failed
```

No lesson content is rewritten. A block keeps pointing at the file it always
pointed at, and the package is found from that.

## How the pieces fit

| Module | Responsibility |
|---|---|
| `paths.py` | On-disk layout, URL shapes, and every path-safety check |
| `probe.py` | Reads ffprobe output, decides what ffmpeg should do — **pure**, no frappe |
| `tokens.py` | Signed short-lived playback tokens — **pure**, no frappe |
| `pipeline.py` | The background job: ffprobe → ffmpeg → packager |
| `api.py` | Endpoints the player calls |
| `uploads.py` | Turning an uploaded File into a packaging job |
| `maintenance.py` | Backfill scanning and cleanup after crashed jobs |

`probe` and `tokens` import nothing from frappe so their logic is unit-testable
without a site — see `lms/tests/test_video_probe.py`.

### Storage

```
sites/<site>/private/files/videos/<video_id>/     # lesson videos (token-gated)
sites/<site>/public/files/videos/<video_id>/      # course preview videos
    manifest.mpd  poster.jpg  probe.json  source.<ext>
    video/init.mp4  video/1.m4s ...
    audio_eng/init.mp4  audio_eng/1.m4s ...
```

Packaging writes to `videos/.tmp/<video_id>/` and renames into place only on
success, so a worker killed mid-encode never leaves a half-manifest a student
could load.

### Authorization

A packaged video is hundreds of files whose paths appear in no lesson content,
so they cannot be gated the way `serve_resource` gates an ordinary upload.
Instead:

1. `get_playback_info` runs the real gate once — the same `can_access_lesson`
   check as every other piece of private lesson media — and mints a token bound
   to `(video, user, expiry)`.
2. Each segment request verifies that token: one HMAC, no database access.

The player renews shortly before expiry rather than waiting for a failure.

### Two details that are easy to get wrong

**Shaka Packager rewrites language codes.** `lang=eng` comes back out of the
manifest as `lang="en"`, `som` as `so`; private-use codes (`qaa`…) pass through.
So `manifest_lang` is *read back out of the generated MPD* rather than assumed —
it is the key the player will report when a learner picks a track.

**Untagged tracks get synthetic codes.** MP4/MOV exports almost never carry
per-track language tags, and two AdaptationSets both claiming `und` collapse into
one entry in any player. Each untagged track is assigned a code from the ISO
639-2 private-use range (`qaa`, `qab`, …), fixed at packaging time. Display names
live in `LMS Video Audio Track.label`, keyed on that code — which is why an
instructor renaming a track is a database write, not a re-encode.

### Watch-duration tracking

`LMS Video Watch Duration` rows and resume positions used to be keyed on
`<video>.src`. Once Shaka attaches a MediaSource that property becomes a `blob:`
URL that differs on every load, so the player publishes a stable
`data-video-source` attribute instead, computed to reproduce exactly what the old
progressive player reported. Existing records keep matching.
