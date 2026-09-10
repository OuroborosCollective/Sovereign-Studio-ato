#!/usr/bin/env bash
# Run-scoped loopback TLS only. No cookie weakening or global certificate bypass.
set -Eeuo pipefail
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GITHUB_ENV:?GITHUB_ENV is required}"
umask 077
TLS_DIR="$(mktemp -d "$RUNNER_TEMP/sovereign-live-tls.XXXXXX")"
CERT="$TLS_DIR/cert.pem"
KEY="$TLS_DIR/key.pem"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -keyout "$KEY" -out "$CERT" -subj '/CN=127.0.0.1' \
  -addext 'subjectAltName=IP:127.0.0.1,DNS:localhost' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign' \
  -addext 'extendedKeyUsage=serverAuth' >/dev/null 2>&1
SPKI="$(openssl x509 -in "$CERT" -pubkey -noout | openssl pkey -pubin -outform DER 2>/dev/null | openssl dgst -sha256 -binary | openssl base64 -A)"
[[ "$SPKI" =~ ^[A-Za-z0-9+/]{43}=$ ]] || { echo 'Invalid local TLS public-key fingerprint' >&2; exit 1; }
openssl verify -CAfile "$CERT" -verify_ip 127.0.0.1 "$CERT" >/dev/null
{
  echo "SOVEREIGN_E2E_TLS_CERT=$CERT"
  echo "SOVEREIGN_E2E_TLS_KEY=$KEY"
  echo "SOVEREIGN_E2E_TLS_SPKI=$SPKI"
  echo "NODE_EXTRA_CA_CERTS=$CERT"
} >> "$GITHUB_ENV"
echo 'Run-scoped loopback HTTPS certificate prepared; private key remains in runner temporary storage.'
