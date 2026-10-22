#!/usr/bin/env bash
# Run a scheduled job's command, and once more after a minute when it failed fast (owner, 22 Oct 2026: "ensure all
# data is getting updated over night without fail or with some retry"). A command that fails within its first
# FAST_S seconds met a refused session, a 5xx or a network blip at the start; one that failed later used its time
# budget, so it is not run again (the job's own timeout would end it half-way) and the next night picks it up.
#   bash scripts/retry.sh <command> [args...]
set -u
FAST_S=${RETRY_FAST_S:-180}
WAIT_S=${RETRY_WAIT_S:-60}
start=$(date +%s)
"$@"
code=$?
took=$(( $(date +%s) - start ))
if [ "$code" -ne 0 ] && [ "$took" -lt "$FAST_S" ]; then
  echo "::warning::'$*' failed after ${took}s (exit $code); trying once more in ${WAIT_S}s"
  sleep "$WAIT_S"
  "$@"
  code=$?
fi
exit "$code"
