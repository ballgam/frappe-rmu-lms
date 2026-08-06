# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""Signed playback tokens for DASH segment requests.

A single video is hundreds of segment files. Running the lesson-resolution gate
(`_resolve_lesson_references`, a LOCATE scan across four content columns) on
every one of them would put a multi-table query in front of every few seconds of
playback, for every concurrent viewer.

So the expensive check runs exactly once, when the player asks for playback info.
On success the user gets a token scoped to that one video; each segment request
then costs one HMAC comparison and no database access at all.

The token is deliberately opaque and self-contained — there is no server-side
session state to store or evict.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

DEFAULT_TTL_HOURS = 12
SEPARATOR = "."


class InvalidToken(Exception):
	"""Raised for any token that is malformed, mismatched, or expired."""


def _b64encode(raw: bytes) -> str:
	return urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
	padding = "=" * (-len(value) % 4)
	return urlsafe_b64decode(value + padding)


def _signature(payload: str, key: str) -> str:
	return _b64encode(hmac.new(key.encode(), payload.encode(), hashlib.sha256).digest())


def mint(video_id: str, user: str, key: str, ttl_hours: float = DEFAULT_TTL_HOURS, now: float | None = None) -> str:
	"""Issue a token for (video_id, user), valid for `ttl_hours`.

	The TTL wants to comfortably outlast one sitting with a long lecture — a
	token expiring mid-playback is recoverable (the player refreshes and retries)
	but visible as a stall.
	"""
	expires_at = int((now if now is not None else time.time()) + ttl_hours * 3600)
	payload = f"{video_id}{SEPARATOR}{user}{SEPARATOR}{expires_at}"
	return f"{_b64encode(payload.encode())}{SEPARATOR}{_signature(payload, key)}"


def verify(token: str, video_id: str, user: str, key: str, now: float | None = None) -> int:
	"""Check a token and return its expiry, or raise InvalidToken.

	Both the video and the user are re-bound here rather than merely read out of
	the token, so a token minted for one video can't be replayed against another,
	and one user's token can't be used on another's session.
	"""
	if not token or not isinstance(token, str):
		raise InvalidToken("missing token")

	parts = token.split(SEPARATOR)
	if len(parts) != 2:
		raise InvalidToken("malformed token")

	encoded_payload, signature = parts
	try:
		payload = _b64decode(encoded_payload).decode()
	except Exception:
		raise InvalidToken("undecodable token")

	# Constant-time compare: a fast-fail string comparison here would leak the
	# expected signature one byte at a time.
	if not hmac.compare_digest(signature.encode(), _signature(payload, key).encode()):
		raise InvalidToken("bad signature")

	# Split from both ends, not on every separator: the user field is an email
	# and routinely contains dots itself (first.last@example.com). video_id is
	# hex and the expiry is an integer, so neither end is ambiguous.
	token_video_id, found_head, rest = payload.partition(SEPARATOR)
	token_user, found_tail, expires_at = rest.rpartition(SEPARATOR)
	if not (found_head and found_tail):
		raise InvalidToken("malformed payload")

	# compare_digest rejects str containing non-ASCII, and a username can be
	# unicode — compare the encoded bytes instead of risking a TypeError.
	if not hmac.compare_digest(token_video_id.encode(), video_id.encode()):
		raise InvalidToken("token is for a different video")

	if not hmac.compare_digest(token_user.encode(), (user or "").encode()):
		raise InvalidToken("token is for a different user")

	try:
		expiry = int(expires_at)
	except ValueError:
		raise InvalidToken("malformed expiry")

	if expiry <= (now if now is not None else time.time()):
		raise InvalidToken("expired")

	return expiry
