#!/usr/bin/env bash
set -euo pipefail

# 🛡️ Sentinel: This script runs inside the reactivecircus/android-emulator-runner
# it is extracted to a separate file to preserve state (variables) and
# ensure proper syntax interpretation for 'if' blocks, as the runner
# executes lines one-by-one in separate shells otherwise.

GHOST_PILOT_APP_PACKAGE="${GHOST_PILOT_APP_PACKAGE:-com.arestudio.nocode.aab}"

adb wait-for-device
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
adb logcat -c

adb logcat *:E > emulator_error.log 2>&1 &
LOGCAT_PID=$!

echo "Starting Ghost Pilot sequence..."
chmod +x test_sequence.sh
bash test_sequence.sh || true

sleep 5
kill "$LOGCAT_PID" || true

echo "=== ERROR SCAN ==="
if grep -Ei "ErrorBoundary|FATAL EXCEPTION|AndroidRuntime|RuntimeError|CRASH|com\.facebook\.react" emulator_error.log; then
  echo "❌ App fatal runtime error detected"
  grep -Ei "ErrorBoundary|FATAL EXCEPTION|AndroidRuntime|RuntimeError|CRASH|com\.facebook\.react" emulator_error.log | head -n 40
  exit 1
fi

if grep -Ei "ANR in ${GHOST_PILOT_APP_PACKAGE}" emulator_error.log; then
  echo "❌ App ANR detected"
  grep -Ei "ANR in ${GHOST_PILOT_APP_PACKAGE}" emulator_error.log | head -n 40
  exit 1
fi

echo "✅ No critical app crash detected"
