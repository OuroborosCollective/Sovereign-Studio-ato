#!/usr/bin/env bash
set +e

APP_PACKAGE="${GHOST_PILOT_APP_PACKAGE:-com.arestudio.nocode.aab}"

echo "[ghost-pilot] Launching ${APP_PACKAGE}"
adb wait-for-device
adb shell monkey -p "$APP_PACKAGE" -c android.intent.category.LAUNCHER 1
sleep 3

echo "[ghost-pilot] Deterministic fallback interaction path"
adb shell input tap 540 1700
sleep 1
adb shell input text "ghostpilot"
sleep 1
adb shell input keyevent 66
sleep 1
adb shell input tap 540 1480
sleep 1
adb shell input swipe 540 1600 540 500 600
sleep 1
adb shell input tap 160 160
sleep 1
adb shell input tap 540 520
sleep 1
adb shell input text "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
sleep 1
adb shell input keyevent 66
sleep 1
adb shell input tap 540 650
sleep 1
adb shell input tap 200 1820
sleep 1
adb shell input tap 540 1820
sleep 1
adb shell input tap 880 1820
sleep 1
adb shell input swipe 900 1200 120 1200 500
sleep 1
adb shell input swipe 120 1200 900 1200 500
sleep 1
adb shell input keyevent 4
sleep 1
