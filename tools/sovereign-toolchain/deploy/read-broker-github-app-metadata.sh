#!/usr/bin/env bash
set -Eeuo pipefail

BROKER_ENV="${1:-}"
if [[ -z "$BROKER_ENV" || ! -f "$BROKER_ENV" || -L "$BROKER_ENV" ]]; then
  printf 'broker metadata file contract invalid\n' >&2
  exit 64
fi

read_literal() {
  local key="$1"
  local raw value=""
  local count=0
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    [[ "$raw" == "$key="* ]] || continue
    count=$((count + 1))
    value="${raw#"$key="}"
    # Required App metadata are unquoted, nonempty literals. This deliberately
    # excludes shell syntax, whitespace, and value interpolation.
    if [[ ! "$value" =~ ^[A-Za-z0-9._/-]+$ ]]; then
      printf 'broker metadata literal invalid for %s\n' "$key" >&2
      exit 65
    fi
  done < "$BROKER_ENV"
  if [[ "$count" -ne 1 ]]; then
    printf 'broker metadata cardinality invalid for %s\n' "$key" >&2
    exit 66
  fi
  printf '%s\n' "$value"
}

for key in \
  SOVEREIGN_MCP_GITHUB_APP_ID \
  SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID \
  SOVEREIGN_MCP_REPOSITORY
do
  if ! value="$(read_literal "$key")"; then
    exit 67
  fi
  printf '%s=%s\n' "$key" "$value"
done
