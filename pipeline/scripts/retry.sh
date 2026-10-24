#!/usr/bin/env bash
# Run a scheduled job's command, and once more after a minute when it failed fast (owner, 22 Oct 2026: "ensure all
# data is getting updated over night without fail or with some retry"). A command that fails within its first
# FAST_S seconds met a 5xx or a network blip at the start; one that failed later used its time budget, so it is not
# run again (the job's own timeout would end it half-way) and the next night picks it up.
# Exit 2 is a refused session (NSE answered 401/403/429): never retried, and remembered for the job in
# $RUNNER_TEMP/source-refused, so the job's later NSE steps (NSE_COMMANDS) are skipped rather than asking NSE again
# and again (nse.py: a refusal is a hard stop; survey, 24 Oct 2026).
#   bash scripts/retry.sh <command> [args...]
set -u
FAST_S=${RETRY_FAST_S:-180}
WAIT_S=${RETRY_WAIT_S:-60}
REFUSED_FLAG="${RUNNER_TEMP:-/tmp}/source-refused"
NSE_COMMANDS=${NSE_COMMANDS:-"governance-sync shareholding-sync pledge-sync deals-sync deals-backfill insider-sync corporate-actions-sync annual-xbrl-catchup sync-companies"}
asks_nse() {
  for word in "$@"; do
    for name in $NSE_COMMANDS; do
      [ "$word" = "$name" ] && return 0
    done
  done
  return 1
}
if [ -e "$REFUSED_FLAG" ] && asks_nse "$@"; then
  echo "::warning::'$*' skipped: NSE refused this job's session earlier ($(cat "$REFUSED_FLAG"))"
  exit 2
fi
start=$(date +%s)
"$@"
code=$?
took=$(( $(date +%s) - start ))
if [ "$code" -eq 2 ]; then
  asks_nse "$@" && echo "$*" > "$REFUSED_FLAG"
  echo "::warning::'$*' was refused (exit 2); not retried"
elif [ "$code" -ne 0 ] && [ "$took" -lt "$FAST_S" ]; then
  echo "::warning::'$*' failed after ${took}s (exit $code); trying once more in ${WAIT_S}s"
  sleep "$WAIT_S"
  "$@"
  code=$?
  [ "$code" -eq 2 ] && asks_nse "$@" && echo "$*" > "$REFUSED_FLAG"
fi
exit "$code"
