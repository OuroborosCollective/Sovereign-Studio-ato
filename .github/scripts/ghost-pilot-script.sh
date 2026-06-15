#!/bin/bash
set -euo pipefail

# This script is used by ghost-pilot.yml to run tests on the emulator.
# It is placed in a separate file to ensure compatibility with reactivecircus/android-emulator-runner@v2,
# which uses /usr/bin/sh as the default shell.

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
