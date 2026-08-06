# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

import click
import frappe
from frappe.commands import get_site, pass_context


@click.command("transcode-lesson-videos")
@click.option("--limit", type=int, default=None, help="Queue at most this many videos.")
@click.option("--lesson", default=None, help="Only consider videos in this Course Lesson.")
@click.option("--retry-failed", is_flag=True, help="Also re-queue videos whose last attempt failed.")
@click.option("--dry-run", is_flag=True, help="List what would be queued and exit.")
@pass_context
def transcode_lesson_videos(context, limit, lesson, retry_failed, dry_run):
	"""Package existing lesson videos for DASH playback.

	Existing lessons keep playing their original file until this runs, so
	backfilling is deliberately opt-in and batched — packaging every video on a
	large site at once would tie up the `long` queue that also carries course
	progress recalculation.

	    bench --site <site> transcode-lesson-videos --limit 10
	"""
	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()

	try:
		from lms.lms.video import maintenance, pipeline

		pending = maintenance.find_unpackaged_lesson_videos(lesson=lesson, include_failed=retry_failed)
		if limit:
			pending = pending[:limit]

		if not pending:
			click.echo("Nothing to do — every lesson video already has a package.")
			return

		if dry_run:
			click.echo(f"Would queue {len(pending)} video(s):")
			for candidate in pending:
				click.echo(f"  {candidate['file_url']}  (lesson: {candidate['lesson']})")
			return

		# Fail loudly and early rather than queueing jobs that will all die the
		# same way two minutes in.
		try:
			click.echo(f"Using packager: {pipeline.check_packager_available()}")
		except Exception as exc:
			click.echo(click.style(f"Shaka Packager is not usable:\n{exc}", fg="red"), err=True)
			raise SystemExit(1)

		queued = maintenance.backfill_lesson_videos(limit=limit, lesson=lesson, include_failed=retry_failed)
		click.echo(f"Queued {len(queued)} video(s) for packaging.")
		for file_url in queued:
			click.echo(f"  {file_url}")
		click.echo("\nWatch progress with: bench --site {0} doctype-list 'LMS Video'".format(site))
	finally:
		frappe.destroy()


@click.command("check-video-pipeline")
@pass_context
def check_video_pipeline(context):
	"""Verify ffmpeg, ffprobe and Shaka Packager are usable on this bench."""
	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()

	try:
		from lms.lms.video import pipeline

		settings = pipeline.get_video_settings()
		ok = True

		for label, resolve in (
			("ffmpeg", pipeline.ffmpeg_binary),
			("ffprobe", pipeline.ffprobe_binary),
		):
			try:
				click.echo(f"{label:10} {click.style('ok', fg='green')}  {resolve(settings)}")
			except Exception as exc:
				ok = False
				click.echo(f"{label:10} {click.style('FAIL', fg='red')}  {exc}")

		try:
			click.echo(f"{'packager':10} {click.style('ok', fg='green')}  {pipeline.check_packager_available(settings)}")
		except Exception as exc:
			ok = False
			click.echo(f"{'packager':10} {click.style('FAIL', fg='red')}  {exc}")

		raise SystemExit(0 if ok else 1)
	finally:
		frappe.destroy()


commands = [transcode_lesson_videos, check_video_pipeline]
