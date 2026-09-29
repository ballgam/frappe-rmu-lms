# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

"""The login page, overridden so it can carry the new student experience.

lms is installed after frappe, and website pages resolve through the installed
apps in reverse, so this page (and its login.html) wins over frappe's. It
builds exactly frappe's context and only adds what the LMS layout needs. The
template then renders frappe's own login.html unchanged unless LMS Settings ›
Enable New Student Experience is on.

The whitelisted endpoints the page's script calls (login_via_key,
send_login_link, ...) are addressed by their frappe.www.login dotted path, so
they are untouched by this override.
"""

import frappe
from frappe.utils import cint
from frappe.www.login import get_context as frappe_get_context

no_cache = True

FRAPPE_DEFAULT_LOGO = "/assets/frappe/images/frappe-framework-logo.svg"
LMS_FALLBACK_LOGO = "/assets/lms/frontend/un-somalia-logo.png"


def get_context(context):
	# Raises frappe.Redirect for a signed-in user, exactly as frappe's does.
	frappe_get_context(context)

	context.lms_new_ui = new_student_ui_enabled()
	if context.lms_new_ui:
		logo = context.get("logo")
		context.lms_logo = logo if logo and logo != FRAPPE_DEFAULT_LOGO else LMS_FALLBACK_LOGO

	return context


def new_student_ui_enabled() -> int:
	"""Read uncached, so switching the setting off takes effect on the next load.

	Before `bench migrate` adds the column the read fails; fall back to frappe's
	page rather than breaking login.
	"""
	try:
		return cint(frappe.db.get_single_value("LMS Settings", "enable_new_student_ui"))
	except Exception:
		return 0
