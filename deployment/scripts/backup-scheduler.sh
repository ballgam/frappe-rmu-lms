#!/usr/bin/env bash
# The first deployment makes a backup immediately; this container repeats it daily.
set -uo pipefail

while true; do
	sleep 86400
	if ! /usr/local/sbin/rmu-lms-backup; then
		echo "Scheduled LMS backup failed; inspect this container's logs." >&2
	fi
done
