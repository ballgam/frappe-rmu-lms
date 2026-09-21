#!/usr/bin/env bash
set -euo pipefail

ffmpeg -version | head -n 1
ffprobe -version | head -n 1
packager --version | grep -F "3.9.3"
node --version | grep -E '^v22\.'
wkhtmltopdf --version | grep -F '0.12.6'

test -x /home/frappe/frappe-bench/env/bin/gunicorn
test -f /home/frappe/frappe-bench/apps/lms/frontend/package.json
test -f /home/frappe/frappe-bench/apps/lms/lms/www/_lms.html
test -d /home/frappe/frappe-bench/assets/lms/frontend
if ! compgen -G '/home/frappe/frappe-bench/assets/lms/frontend/assets/shaka-player.compiled-*.js' >/dev/null; then
	echo "The compiled Shaka Player asset is missing." >&2
	exit 1
fi
test ! -d /home/frappe/frappe-bench/apps/lms/frontend/node_modules

python - <<'PY'
import sys

sys.path.insert(0, "/home/frappe/frappe-bench/apps/frappe")
import frappe

assert frappe.__version__ == "15.116.1", frappe.__version__
print(f"Frappe {frappe.__version__}")
PY

if find /home/frappe/frappe-bench/apps -type d -name .git -print -quit | grep -q .; then
	echo "Git metadata leaked into the runtime image." >&2
	exit 1
fi

if [[ -S /var/run/docker.sock ]]; then
	echo "The Docker socket must not be mounted in the application image." >&2
	exit 1
fi

echo "Image smoke checks passed."
