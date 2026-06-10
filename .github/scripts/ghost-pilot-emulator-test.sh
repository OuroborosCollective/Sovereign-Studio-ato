#!/usr/bin/env bash
set -e

# Inherit env vars from GitHub Action
APP_PACKAGE="${GHOST_PILOT_APP_PACKAGE:-com.arestudio.nocode.aab}"

echo "Waiting for device..."
adb wait-for-device
echo "Installing APK..."
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
echo "Clearing logcat..."
adb logcat -c

echo "Starting logcat background process..."
adb logcat *:E > emulator_error.log 2>&1 &
LOGCAT_PID=$!

echo "Starting Ghost Pilot sequence..."
chmod +x test_sequence.sh
bash test_sequence.sh || true

echo "Waiting for logs to settle..."
sleep 5

if [ -n "$LOGCAT_PID" ]; then
  echo "Stopping logcat (PID: $LOGCAT_PID)..."
  kill "$LOGCAT_PID" || true
fi

echo "=== ERROR SCAN ==="
if grep -Ei "ErrorBoundary|FATAL EXCEPTION|AndroidRuntime|RuntimeError|CRASH|com\.facebook\.react" emulator_error.log; then
  echo "❌ App fatal runtime error detected"
  grep -Ei "ErrorBoundary|FATAL EXCEPTION|AndroidRuntime|RuntimeError|CRASH|com\.facebook\.react" emulator_error.log | head -n 40
  exit 1
fi

if grep -Ei "ANR in ${APP_PACKAGE}" emulator_error.log; then
  echo "❌ App ANR detected"
  grep -Ei "ANR in ${APP_PACKAGE}" emulator_error.log | head -n 40
  exit 1
fi

echo "✅ No critical app crash detected"
