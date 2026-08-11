import frappe


def execute():
	"""Backfill `origin` and `status` on audio tracks that predate added tracks.

	Every row that exists before this patch came out of its video's original
	upload and is fully packaged, so it is a Ready "Source File" track. The
	columns are new, so existing rows hold NULL rather than the field defaults —
	and the player-facing track list filters on `status`, which would hide every
	track on every video until this runs.
	"""
	table = "`tabLMS Video Audio Track`"

	frappe.db.sql(f"update {table} set origin = 'Source File' where ifnull(origin, '') = ''")
	frappe.db.sql(f"update {table} set status = 'Ready' where ifnull(status, '') = ''")
