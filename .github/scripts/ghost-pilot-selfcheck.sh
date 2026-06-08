#!/usr/bin/env bash
set -euo pipefail

export GHOST_PILOT_APP_PACKAGE="${GHOST_PILOT_APP_PACKAGE:-com.arestudio.nocode.aab}"
export GHOST_PILOT_MIN_COMMANDS="${GHOST_PILOT_MIN_COMMANDS:-8}"
export GHOST_PILOT_MIN_MEANINGFUL_COMMANDS="${GHOST_PILOT_MIN_MEANINGFUL_COMMANDS:-4}"

bash .github/scripts/ghost-pilot-generate-sequence.sh

grep -q 'DEGRADED_BUT_TESTED' ghost_pilot_status.txt
grep -q "${GHOST_PILOT_APP_PACKAGE}" test_sequence.sh

command_count=$(grep -Ec '^adb shell input (tap|text|keyevent|swipe)\b' test_sequence.sh || true)
meaningful_count=$(grep -Ec '^adb shell input (tap|text|swipe)\b' test_sequence.sh || true)

if [ "$command_count" -lt "$GHOST_PILOT_MIN_COMMANDS" ]; then
  echo "expected at least ${GHOST_PILOT_MIN_COMMANDS} commands, got ${command_count}"
  exit 1
fi

if [ "$meaningful_count" -lt "$GHOST_PILOT_MIN_MEANINGFUL_COMMANDS" ]; then
  echo "expected at least ${GHOST_PILOT_MIN_MEANINGFUL_COMMANDS} meaningful commands, got ${meaningful_count}"
  exit 1
fi

echo "[ghost-pilot-selfcheck] ok"
