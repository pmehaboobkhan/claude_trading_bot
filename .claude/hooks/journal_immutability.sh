#!/usr/bin/env bash
# Block edits to journal files dated more than 24 hours ago.
source "$(dirname "$0")/_lib.sh"
read_hook_input

file_path="$(hook_field tool_input.file_path)"
[ -z "$file_path" ] && allow

# Match journals/daily/YYYY-MM-DD.md
case "$file_path" in
  *journals/daily/*.md)
    base="$(basename "$file_path" .md)"
    # Expect base = YYYY-MM-DD
    if ! echo "$base" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
      allow  # not a dated journal file
    fi
    today_epoch=$(date +%s)
    file_epoch=$(date -j -f "%Y-%m-%d" "$base" +%s 2>/dev/null || python3 -c "
import sys, time, datetime
print(int(time.mktime(datetime.datetime.strptime(sys.argv[1], '%Y-%m-%d').timetuple())))
" "$base")
    age_seconds=$(( today_epoch - file_epoch ))
    # 25h grace window for late same-day finalization
    if [ "$age_seconds" -gt 90000 ]; then
      block "journal $file_path is older than 24h and is immutable"
    fi
    ;;
  *journals/weekly/*.md|*journals/monthly/*.md)
    # Weekly/monthly editing logic: allow only the file matching the current period.
    # For v1 keep simple — let humans + journal agent manage; relax if needed.
    allow
    ;;
esac

allow
