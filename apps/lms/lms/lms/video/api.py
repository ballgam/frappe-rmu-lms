# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""Endpoints the player calls: playback info, manifest, segments, track labels.

The access model has two halves. `get_playback_info` runs the real, expensive
permission check — the same `can_access_lesson` gate that guards every other
piece of private lesson media — and hands back a token. Every subsequent segment
request is then authorized by verifying that token, which costs one HMAC and no
database round trip. See `tokens` for why that split exists.
"""

from __future__ import annotations

import mimetypes
import os
import re
import time
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.password import get_encryption_key
from frappe.utils.response import send_private_file
from werkzeug.wrappers import Response

from lms.lms.video import paths, pipeline, tokens

SEGMENT_ENDPOINT = "/api/method/lms.lms.video.api.serve_video_segment"
MANIFEST_ENDPOINT = "/api/method/lms.lms.video.api.serve_video_manifest"

MANIFEST_CONTENT_TYPE = "application/dash+xml"

#: SegmentTemplate attributes holding a segment URL template.
TEMPLATE_ATTRIBUTES = ("initialization", "media")


def _signing_key() -> str:
	return get_encryption_key()


def _token_ttl() -> float:
	return pipeline.get_video_settings().video_token_ttl_hours


VIDEO_FIELDS = [
	"name",
	"video_id",
	"status",
	"is_private",
	"duration",
	"manifest_url",
	"poster_url",
	"source_file_url",
	"error_log",
]


def _get_video(video_id: str = None, file_url: str = None):
	"""Look a video up by its id, or by the source file a lesson block points at.

	The `file_url` route is what lets already-published lessons gain an audio
	menu with no edit to their content: an upload block keeps pointing at the
	file it always pointed at, and the package is found from that.
	"""
	if video_id:
		if not paths.is_valid_video_id(video_id):
			frappe.throw(_("Invalid video id"), frappe.DoesNotExistError)
		filters = {"video_id": video_id}
	elif file_url:
		filters = {"source_file_url": file_url}
	else:
		frappe.throw(_("A video id or file url is required"), frappe.DoesNotExistError)

	doc = frappe.db.get_value("LMS Video", filters, VIDEO_FIELDS, as_dict=True)
	if not doc:
		frappe.throw(_("Video not found"), frappe.DoesNotExistError)
	return doc


def _assert_can_play(doc):
	"""The one expensive gate, run once per playback session.

	A public video (a course preview) is guest-visible by design and needs no
	check. A private one is lesson media, so it is authorized exactly the way
	`serve_resource` authorizes every other private lesson file: find the lessons
	that reference it, and ask whether this user can reach any of them.
	"""
	if not cint(doc.is_private):
		return

	from lms.lms.permissions import can_access_lesson

	references = _lesson_references(doc)
	if not references:
		_deny(doc.video_id, "video not referenced by any lesson")
		raise frappe.PermissionError

	if not any(
		can_access_lesson(lesson, instructor_only=instructor_only) for lesson, instructor_only in references
	):
		_deny(doc.video_id, "can_access_lesson denied for all references")
		raise frappe.PermissionError


def _assert_can_edit(doc):
	"""Editing track labels is an authoring action, gated like lesson authoring."""
	from lms.lms.permissions import can_access_lesson

	roles = frappe.get_roles()
	if "Moderator" in roles or "Course Creator" in roles:
		return

	if not any(
		can_access_lesson(lesson, instructor_only=True) for lesson, _instructor_only in _lesson_references(doc)
	):
		_deny(doc.video_id, "not an instructor on any referencing lesson")
		raise frappe.PermissionError


def _lesson_references(doc) -> list[tuple[str, bool]]:
	"""Lessons that embed this video, via either the source upload or the manifest.

	Lesson content references the *uploaded* file; the manifest url only appears
	once a block has been migrated to it. Accept either so the gate holds through
	the migration.
	"""
	from lms.lms.doctype.course_lesson.course_lesson import _resolve_lesson_references

	references: list[tuple[str, bool]] = []
	for url in filter(None, (doc.source_file_url, doc.manifest_url)):
		references.extend(_resolve_lesson_references(url))
	return references


def _deny(video_id, reason):
	frappe.logger("lms.security").warning(
		"Video access denied: user=%s video_id=%s reason=%s", frappe.session.user, video_id, reason
	)


def _verify_token(video_id: str, token: str):
	try:
		tokens.verify(token, video_id, frappe.session.user, _signing_key())
	except tokens.InvalidToken as exc:
		_deny(video_id, f"token rejected: {exc}")
		# 403 rather than 401: the player's response filter refreshes on 403 and
		# retries, which is how a token expiring mid-lecture recovers.
		raise frappe.PermissionError(_("Playback token is not valid: {0}").format(exc))


TRACK_FIELDS = [
	"name",
	"manifest_lang",
	"segment_dir",
	"language",
	"label",
	"is_default",
	"channels",
	"codec",
	"track_index",
	"origin",
	"status",
	"source_file_url",
	"error_log",
]


def _audio_track_rows(video_name: str) -> list[dict]:
	"""Every audio track row, whatever state it is in. Authoring view."""
	rows = frappe.get_all(
		"LMS Video Audio Track",
		filters={"parent": video_name, "parenttype": "LMS Video"},
		fields=TRACK_FIELDS,
		order_by="idx asc",
	)
	return [
		{
			"manifest_lang": row.manifest_lang,
			"language": row.language or "",
			# `label` is what the audio menu shows. It lives here rather than in
			# the manifest precisely so an instructor can fix it without a re-encode.
			"label": row.label or row.manifest_lang,
			"is_default": bool(row.is_default),
			"channels": row.channels,
			"codec": row.codec or "",
			# Rows predating the added-track feature carry no status; they are all
			# fully packaged tracks from the original upload.
			"status": row.status or "Ready",
			"origin": row.origin or "Source File",
			"error": row.error_log or None,
		}
		for row in rows
	]


def _audio_tracks_for(video_name: str) -> list[dict]:
	"""The tracks a learner may be offered.

	Filtered to the ones that are actually in the manifest: a track still being
	imported has no segments on disk yet, so offering it would put a dead entry
	in the audio menu.
	"""
	return [track for track in _audio_track_rows(video_name) if track["status"] == "Ready"]


@frappe.whitelist(allow_guest=True)
def get_playback_info(video_id: str = None, file_url: str = None) -> dict:
	"""Everything the player needs to start, including a scoped playback token."""
	doc = _get_video(video_id, file_url)
	_assert_can_play(doc)

	is_private = bool(cint(doc.is_private))
	info = {
		"video_id": doc.video_id,
		"status": doc.status,
		"is_private": is_private,
		"duration": doc.duration,
		"audio_tracks": _audio_tracks_for(doc.name) if doc.status == "Ready" else [],
		"error": doc.error_log if doc.status == "Failed" else None,
		# While packaging (or after a failure) the block falls back to the
		# original upload, so a lesson is never dark waiting on a transcode.
		"fallback_url": _fallback_url(doc, is_private),
		"token": None,
		"token_expires_at": None,
		"manifest_url": None,
		"poster_url": None,
	}

	if doc.status != "Ready":
		return info

	if is_private:
		info.update(_mint(doc.video_id))
		info["manifest_url"] = f"{MANIFEST_ENDPOINT}?video_id={doc.video_id}"
		# The poster is loaded by the browser straight off the <video> element, so
		# it never passes through the player's request filter — its token has to
		# be part of the url.
		info["poster_url"] = (
			f"{SEGMENT_ENDPOINT}?video_id={doc.video_id}"
			f"&path={paths.POSTER_NAME}&t={quote(info['token'])}"
		)
	else:
		# Public packages are plain files under public/files, served by the web
		# server with no Python in the path at all.
		info["manifest_url"] = doc.manifest_url
		info["poster_url"] = doc.poster_url

	return info


def _mint(video_id: str) -> dict:
	"""A token plus the moment it stops working.

	Handing the expiry back lets the player renew shortly *before* the deadline
	instead of discovering it through a failed segment mid-sentence.
	"""
	ttl = _token_ttl()
	token = tokens.mint(video_id, frappe.session.user, _signing_key(), ttl_hours=ttl)
	return {"token": token, "token_expires_at": int(time.time() + ttl * 3600)}


def _fallback_url(doc, is_private: bool) -> str | None:
	if not doc.source_file_url:
		return None
	if not is_private:
		return doc.source_file_url

	from lms.lms.utils import private_media_url

	return private_media_url(doc.source_file_url)


@frappe.whitelist(allow_guest=True)
def refresh_playback_token(video_id: str) -> dict:
	"""Re-run the full gate and issue a fresh token.

	Called by the player when a segment request comes back 403, which is what a
	token expiring part-way through a long lecture looks like.
	"""
	doc = _get_video(video_id)
	_assert_can_play(doc)

	if not cint(doc.is_private):
		return {"token": None, "token_expires_at": None}

	return _mint(doc.video_id)


def rewrite_manifest_urls(manifest: str, video_id: str) -> str:
	"""Point every segment template at the token-gated endpoint.

	A DASH player resolves the relative segment templates in a manifest against
	the manifest's own URL. Our private manifest is served from
	`/api/method/...serve_video_manifest?video_id=X`, so `video/1.m4s` would
	resolve to `/api/method/video/1.m4s` and every segment would 404 — the same
	trap that makes `rewrite_private_media` unsafe for these files.

	Rewriting the templates to absolute paths sidesteps resolution entirely.
	`$Number$` survives untouched: the player substitutes it textually before it
	ever builds the request.

	The token is deliberately *not* baked in here. It is appended per-request by
	the player, so refreshing an expired one doesn't require re-fetching the
	manifest.
	"""

	def replace(match: re.Match) -> str:
		attribute, value = match.group(1), match.group(2)
		if value.startswith("/") or "://" in value:
			return match.group(0)
		return f'{attribute}="{SEGMENT_ENDPOINT}?video_id={video_id}&path={value}"'

	return re.sub(
		rf'\b({"|".join(TEMPLATE_ATTRIBUTES)})="([^"]+)"',
		replace,
		manifest,
	)


@frappe.whitelist(allow_guest=True)
def serve_video_manifest(video_id: str, t: str = None):
	doc = _get_video(video_id)

	if not cint(doc.is_private):
		# Public packages don't go through here at all; if something asks anyway,
		# hand back the real path rather than serving it twice.
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = doc.manifest_url
		return

	_verify_token(video_id, t)

	if doc.status != "Ready":
		frappe.throw(_("This video is still being processed."), frappe.DoesNotExistError)

	path = paths.manifest_path(video_id, is_private=True)
	if not os.path.isfile(path):
		frappe.throw(_("Manifest is missing for this video."), frappe.DoesNotExistError)

	with open(path) as handle:
		manifest = rewrite_manifest_urls(handle.read(), video_id)

	response = Response(manifest, content_type=MANIFEST_CONTENT_TYPE)
	# The manifest embeds no token, but it is per-video and cheap to rebuild;
	# a shared cache must never hold one user's copy for another.
	response.headers["Cache-Control"] = "private, no-store"
	return response


@frappe.whitelist(allow_guest=True)
def serve_video_segment(video_id: str, path: str, t: str = None):
	"""Serve one segment (or the poster) after verifying the playback token.

	This is the hot path — hundreds of calls per video — so it deliberately does
	no database work beyond the single row lookup needed to know whether the
	video is private.
	"""
	doc = _get_video(video_id)
	is_private = bool(cint(doc.is_private))

	# The poster sits at the folder root rather than in a stream sub-folder, so
	# it is the one filename allowed to have no directory component.
	is_poster = path == paths.POSTER_NAME

	if is_private:
		_verify_token(video_id, t)

	if is_poster:
		absolute = os.path.join(paths.video_dir(video_id, is_private=is_private), paths.POSTER_NAME)
	else:
		absolute = paths.resolve_inside(video_id, path, is_private=is_private)

	if not os.path.isfile(absolute):
		raise frappe.DoesNotExistError

	if not is_private:
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = paths.video_url(video_id, path, is_private=False)
		return

	# send_private_file wants a path relative to the site's private/ directory.
	# Deriving it by splitting on the literal "/private" (as the older
	# serve_resource does) breaks whenever the bench itself lives under a path
	# containing that word, so compute it against the real root instead.
	private_root = frappe.get_site_path(frappe.local.conf.get("private_path", "private"))
	response = send_private_file(os.path.relpath(absolute, os.path.realpath(private_root)))

	# Segments are immutable — a given path always holds the same bytes — so they
	# can be cached hard for the life of the token that fetched them.
	response.headers["Cache-Control"] = f"private, max-age={int(_token_ttl() * 3600)}"
	if not response.headers.get("Content-Type"):
		response.headers["Content-Type"] = (
			mimetypes.guess_type(absolute)[0] or "application/octet-stream"
		)
	return response


@frappe.whitelist()
def list_audio_tracks(video_id: str) -> dict:
	"""The authoring view of a video's tracks, including ones still importing.

	`get_playback_info` deliberately hides everything that is not `Ready`, since
	it feeds the learner's audio menu. The editor needs exactly what that hides:
	which tracks are queued, how far along they are, and why one failed.
	"""
	doc = _get_video(video_id)
	_assert_can_edit(doc)

	return {
		"video_id": doc.video_id,
		"status": doc.status,
		"duration": doc.duration,
		"audio_tracks": _audio_track_rows(doc.name),
	}


@frappe.whitelist()
def update_audio_tracks(video_id: str, tracks) -> dict:
	"""Rename / re-language the audio tracks an instructor sees in the menu.

	Purely a database update. The manifest is keyed on `manifest_lang`, which is
	never touched here, so relabelling a two-hour lecture's tracks is instant
	rather than a re-encode.
	"""
	if isinstance(tracks, str):
		tracks = frappe.parse_json(tracks)

	doc_meta = _get_video(video_id)
	_assert_can_edit(doc_meta)

	doc = frappe.get_doc("LMS Video", doc_meta.name)
	by_lang = {row.get("manifest_lang"): row for row in (tracks or [])}

	for row in doc.audio_tracks:
		update = by_lang.get(row.manifest_lang)
		if not update:
			continue
		row.label = (update.get("label") or "").strip() or row.manifest_lang
		row.language = (update.get("language") or "").strip()
		row.is_default = cint(update.get("is_default"))

	doc.save(ignore_permissions=True)
	# The authoring view, since this is only ever called from the editor — a
	# track still importing has to keep its row in the list it was renamed in.
	return {"audio_tracks": _audio_track_rows(doc.name)}
