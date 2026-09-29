# Copyright (c) 2026, Frappe and Contributors
# See license.txt

"""The lms override of /login (lms/www/login.py + login.html).

With LMS Settings › Enable New Student Experience off it must be frappe's page,
untouched. With it on, the new layout must still carry every hook frappe's
login.js looks the page up by, or password login, OTP, forgot-password and
sign-up silently stop working.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response_content

# What frappe's login.js finds the page by (templates/includes/login/login.js).
LOGIN_JS_CONTRACT = [
	'class="form-signin form-login"',
	'id="login_email"',
	'id="login_password"',
	'class="toggle-password',
	"btn-login",
	"login-content page-card",
	"page-card-body",
	"class='for-login'",
	"for-signup",
	"class='for-forgot'",
	"form-forgot hide",
	'id="forgot_email"',
	"class='for-login-with-email-link'",
	"form-login-with-email-link hide",
	'id="login_with_email_link_email"',
	'href="#forgot"',
	"login.bundle.css",
]


class TestNewStudentUILogin(FrappeTestCase):
	def setUp(self):
		self.original = frappe.db.get_single_value("LMS Settings", "enable_new_student_ui")
		frappe.set_user("Guest")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("LMS Settings", "enable_new_student_ui", self.original or 0)

	def render_login(self, enabled: int) -> str:
		frappe.db.set_single_value("LMS Settings", "enable_new_student_ui", enabled)
		# The page reads frappe.local.request (e.g. ?redirect-to=), as it would
		# in a browser.
		set_request(method="GET", path="/login")
		return get_response_content("login")

	def test_flag_off_renders_frappes_page(self):
		html = self.render_login(0)
		self.assertNotIn("lms-login", html)
		# Frappe's form, not an error page (which would also lack lms-login).
		self.assertIn('id="login_email"', html)
		self.assertIn('id="login_password"', html)

	def test_flag_on_renders_lms_layout(self):
		html = self.render_login(1)
		self.assertIn('class="lms-login"', html)
		self.assertIn("/assets/lms/css/lms_login.css", html)

	def test_flag_on_keeps_login_js_contract(self):
		html = self.render_login(1)
		for hook in LOGIN_JS_CONTRACT:
			with self.subTest(hook=hook):
				self.assertIn(hook, html)
