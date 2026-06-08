#!/usr/bin/env bash
set -euo pipefail

: "${GHOST_PILOT_APP_PACKAGE:=com.arestudio.nocode.aab}"
: "${GHOST_PILOT_MIN_COMMANDS:=8}"
: "${GHOST_PILOT_MIN_MEANINGFUL_COMMANDS:=4}"

FALLBACK_SCRIPT=".github/scripts/ghost-pilot-fallback-adb.sh"

prepare_context() {
  if [ -f "android/app/src/main/res/values/strings.xml" ]; then
    cat "android/app/src/main/res/values/strings.xml" > strings_extracted.txt
  else
    echo "Empty Strings" > strings_extracted.txt
  fi

  if [ -f "src/App.tsx" ]; then
    cat "src/App.tsx" > app_extracted.txt
  elif [ -f "App.tsx" ]; then
    cat "App.tsx" > app_extracted.txt
  else
    echo "Empty Code" > app_extracted.txt
  fi
}

write_fallback_sequence() {
  local reason="$1"
  echo "$reason" > ghost_pilot_status.txt
  cp "$FALLBACK_SCRIPT" test_sequence.sh
  chmod +x test_sequence.sh
}

validate_sequence() {
  local file="$1"
  [ -s "$file" ] || return 1

  local command_count meaningful_count escape_count
  command_count=$(grep -Ec '^adb shell input (tap|text|keyevent|swipe)\b' "$file" || true)
  meaningful_count=$(grep -Ec '^adb shell input (tap|text|swipe)\b' "$file" || true)
  escape_count=$(grep -Ec '^adb shell input keyevent (3|4|HOME|BACK)\b' "$file" || true)

  if [ "$command_count" -lt "$GHOST_PILOT_MIN_COMMANDS" ]; then
    echo "[ghost-pilot] Invalid sequence: only ${command_count} adb input commands."
    return 1
  fi

  if [ "$meaningful_count" -lt "$GHOST_PILOT_MIN_MEANINGFUL_COMMANDS" ]; then
    echo "[ghost-pilot] Invalid sequence: only ${meaningful_count} meaningful commands."
    return 1
  fi

  if [ "$command_count" -eq "$escape_count" ]; then
    echo "[ghost-pilot] Invalid sequence: only HOME/BACK keyevents."
    return 1
  fi

  return 0
}

prepare_context

STRINGS_ESCAPED=$(jq -Rs . < strings_extracted.txt)
APP_ESCAPED=$(jq -Rs . < app_extracted.txt)

QUERY="Analyze this Android app context and return only safe adb shell input commands. Include taps, swipes, text input, enter, and back. Return at least ${GHOST_PILOT_MIN_COMMANDS} commands. Do not return only HOME/BACK.

Strings:
${STRINGS_ESCAPED}

Code:
${APP_ESCAPED}"

PAYLOAD=$(jq -n --arg q "$QUERY" '{contents: [{parts: [{text: $q}]}], generationConfig: {temperature: 0.2, topP: 0.8, maxOutputTokens: 2048}}')

echo "$PAYLOAD" > payload.json
: > response.json
: > model_used.txt

if [ -z "${GEMINI_API_KEY:-}" ]; then
  write_fallback_sequence "DEGRADED_BUT_TESTED: missing GEMINI_API_KEY"
else
  MODELS=()
  if [ -n "${GEMINI_MODEL:-}" ]; then
    MODELS+=("$GEMINI_MODEL")
  fi
  MODELS+=("gemini-2.5-flash" "gemini-2.5-flash-lite" "gemini-flash-latest")

  for model in "${MODELS[@]}"; do
    safe_model=$(echo "$model" | tr '/:' '__')
    echo "[ghost-pilot] Trying Gemini model: ${model}"

    http_code=$(curl -sS -w "%{http_code}" -o "response.${safe_model}.json" -X POST \
      "https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent" \
      -H "Content-Type: application/json" \
      -H "x-goog-api-key: ${GEMINI_API_KEY}" \
      -d @payload.json || true)

    cp "response.${safe_model}.json" response.json

    if [[ "$http_code" != 2* ]]; then
      echo "[ghost-pilot] Model ${model} failed with HTTP ${http_code}."
      continue
    fi

    COMMANDS=$(jq -r '.candidates[0].content.parts[0].text // empty' response.json \
      | sed 's/```bash//g' \
      | sed 's/```//g' \
      | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
      | grep -E '^adb shell input (tap|text|keyevent|swipe)\b' \
      || true)

    {
      echo '#!/usr/bin/env bash'
      echo 'set +e'
      echo 'APP_PACKAGE="${GHOST_PILOT_APP_PACKAGE:-com.arestudio.nocode.aab}"'
      echo 'adb wait-for-device'
      echo 'adb shell monkey -p "$APP_PACKAGE" -c android.intent.category.LAUNCHER 1'
      echo 'sleep 3'
      echo "$COMMANDS"
    } > test_sequence.sh
    chmod +x test_sequence.sh

    if validate_sequence test_sequence.sh; then
      echo "$model" > model_used.txt
      echo "AI_GENERATED_AND_VALIDATED: ${model}" > ghost_pilot_status.txt
      break
    fi
  done

  if ! validate_sequence test_sequence.sh; then
    write_fallback_sequence "DEGRADED_BUT_TESTED: Gemini unavailable or returned weak sequence"
  fi
fi

echo "=== GHOST PILOT STATUS ==="
cat ghost_pilot_status.txt

echo "=== MODEL USED ==="
cat model_used.txt || true

echo "=== FINAL COMMANDS ==="
cat test_sequence.sh
