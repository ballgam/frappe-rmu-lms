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
# Start Docker Desktop first on macOS and Windows.
docker pull google/shaka-packager
```

If your deployment image already bundles the binary, switch
LMS Settings → Video Processing → *Shaka Packager Mode* to `Binary`.

**3. Verify** before relying on it:

```bash
bench --site <site> check-video-pipeline
```

If the command says that it cannot connect to `docker.sock`, start Docker
Desktop and wait until it reports that the engine is running. If it says a
configured packager path is not executable, select `Docker` in LMS Settings →
Video Processing and clear **Shaka Packager Path**; that field only applies in
`Binary` mode. The settings form rejects an invalid configured executable, and
adding a track runs the full check again before it queues a worker.

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

## Adding an audio track later

Translations arrive late. A lecture is recorded, packaged and published, and the
Somali narration turns up three months afterwards. Re-uploading the lecture would
orphan its `LMS Video`, its watch-duration records and every lesson referencing
it, so instead the new track is grafted onto the package that already exists:

```
upload audio → ffprobe → ffmpeg (one track) → shaka-packager → audio_<lang>/
                                                                    ↓
                                            one <AdaptationSet> merged into manifest.mpd
```

**The video is never touched.** Its segments are not read, rewritten or
re-encoded — only a new folder appears beside them and the manifest gains one
entry. A two-hour lecture gains a dub in about a minute, and a learner watching
while it happens sees nothing until they reload.

Instructors reach it from the lesson editor: **Audio Tracks → Add an audio
track**. An audio file or a re-dubbed video both work; for a video, its first
audio stream is taken. Removing a track is the same machinery in reverse.

If a prior import failed because the packager was unavailable, restore the
pipeline first with `check-video-pipeline`, then use **Retry** on the intended
track. Remove duplicate failed rows rather than retrying each one: every retry
imports one separate selectable narration.

### Why the upload has its own endpoint

`frappe.handler.upload_file` refuses every `audio/*` mimetype for users without
desk access — its `ALLOWED_MIMETYPES` admits `video/mp4` and `video/quicktime`
and no audio at all. Course creators here are Website Users, so uploading a
lecture works and uploading its translated narration comes back **417** before
any of this app's code runs.

Rather than loosening that list site-wide, the upload posts to
`audio_tracks.upload_audio_source` (via the uploader's `upload_endpoint`), which
gates on the narrower question — may this user edit *this video's* tracks —
and still enforces the file type, privacy and the site's own size ceiling.

That ceiling is `max_file_size`, 25 MB by default, which no real dub fits under
either. Raise it alongside the video limit:

```bash
bench --site <site> set-config max_file_size 2147483648   # 2 GB
```

### What keeps it safe

**The manifest is the commit point.** Segments are copied in first, where nothing
references them, and the manifest is swapped with `os.replace`. Every readable
state of the folder is a consistent one, so a worker killed mid-import leaves the
package exactly as it was.

**One drain per video.** Every add and remove for a video runs in one job,
deduplicated on the video and guarded by a file lock — two workers doing a
read-modify-write on one `manifest.mpd` would lose an AdaptationSet.

**Added tracks always get a private-use code.** The packager rewrites real
language codes on their way into the MPD (`fra` becomes `fr`), so asking for a
real code risks colliding with an AdaptationSet that is already there *after*
that rewrite — and two sets sharing a `lang` collapse into one entry in every
player, losing a track rather than adding one. The instructor's real language
lives in `language` and the display name in `label`, exactly as it already does
for untagged tracks.

**Imported audio is padded or trimmed to the video's exact duration** (`apad` plus
`-t`), because a manifest that ends before a track does truncates that track's
tail. A file more than 2% (minimum 5s) off is rejected outright while the upload
dialog is still open: a forty-minute file against a ninety-minute lecture is the
wrong upload, not something to pad with fifty minutes of silence.

**A full repackage does not lose translations.** `retry_packaging` rebuilds the
track list from the source file, which knows nothing about tracks added later, so
those rows are carried across, re-assigned a free code and re-imported from the
files they came from. A track whose source file has since been deleted is left
visible and `Failed` rather than vanishing.

Track state lives on the row (`status`, `origin`, `source_file_url`), not on the
video: `LMS Video.status` stays `Ready` for the whole operation, which is what
keeps learners playing. `get_playback_info` therefore returns only `Ready` rows,
while `list_audio_tracks` — the authoring view — returns all of them.

## How the pieces fit

| Module | Responsibility |
|---|---|
| `paths.py` | On-disk layout, URL shapes, and every path-safety check |
| `probe.py` | Reads ffprobe output, decides what ffmpeg should do — **pure**, no frappe |
| `manifest.py` | Reading and editing a DASH manifest in place — **pure**, no frappe |
| `tokens.py` | Signed short-lived playback tokens — **pure**, no frappe |
| `pipeline.py` | The background job: ffprobe → ffmpeg → packager |
| `audio_tracks.py` | Adding and removing tracks on a package that already exists |
| `api.py` | Endpoints the player calls |
| `uploads.py` | Turning an uploaded File into a packaging job |
| `maintenance.py` | Backfill scanning and cleanup after crashed jobs |

`probe`, `manifest` and `tokens` import nothing from frappe so their logic is
unit-testable without a site — see `lms/tests/test_video_probe.py`,
`test_video_manifest.py` and `test_video_audio_commands.py`.

### Storage

```
sites/<site>/private/files/videos/<video_id>/     # lesson videos (token-gated)
sites/<site>/public/files/videos/<video_id>/      # course preview videos
    manifest.mpd  poster.jpg  probe.json  source.<ext>
    video/init.mp4  video/1.m4s ...
    audio_eng/init.mp4  audio_eng/1.m4s ...
    audio_qaa/init.mp4  audio_qaa/1.m4s ...   # a track added later
```

Packaging writes to `videos/.tmp/<video_id>/` and renames into place only on
success, so a worker killed mid-encode never leaves a half-manifest a student
could load. Importing one audio track stages under
`videos/.tmp/tracks/<video_id>/<operation>/` — a sibling, so a full repackage's
`rmtree` of its own staging cannot destroy an import in flight.

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
