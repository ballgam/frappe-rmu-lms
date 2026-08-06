# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""DASH packaging and playback for uploaded lesson videos.

Modules:
    paths     — on-disk layout, url shapes, and the path-safety checks
    probe     — reads ffprobe output and decides what ffmpeg should do (pure)
    tokens    — signed short-lived playback tokens (pure)
    pipeline  — the background job: ffprobe -> ffmpeg -> shaka-packager
    api       — whitelisted endpoints the player calls

`probe` and `tokens` deliberately import nothing from frappe so their logic can
be unit-tested without a site; keep this package's __init__ free of imports for
the same reason.
"""
