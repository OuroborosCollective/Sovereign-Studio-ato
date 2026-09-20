#!/usr/bin/env python3
"""Read bounded Agent Zero routing metadata over pinned, password-only SSH.

Run in an owner-operated terminal with Paramiko installed. The password is read
with getpass after host-key verification and is never saved. No runtime mutation,
model call, raw settings, environment dump or conversation logs are performed.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import re
import shlex
import socket
import sys
import time


# Only allowlisted fields leave the container. Unknown configuration remains
# unknown; an installed source hash does not prove what a running process loaded.
CONTAINER_PROBE = r'''
import hashlib, importlib.metadata, json, re
from pathlib import Path
from urllib.parse import urlsplit

def identifier(value):
    text = str(value or '')
    if re.search(r'(?:sk-|gh[pousr]_|token|secret|password|bearer)', text, re.I):
        return 'REDACTED'
    return text if re.fullmatch(r'[A-Za-z0-9_./:@+ -]{0,160}', text) else 'REDACTED'

def endpoint(value):
    try:
        url = urlsplit(str(value or ''))
        if url.scheme not in ('http', 'https') or not url.hostname:
            return None
        return {'scheme': url.scheme, 'host': url.hostname, 'port': url.port,
                'path': url.path if re.fullmatch(r'/[A-Za-z0-9/_.-]{0,100}', url.path) else 'REDACTED'}
    except ValueError:
        return None

out = {'schemaVersion': 'sovereign.agent-zero-route-readback.v1',
       'sourceHashes': {}, 'settings': [], 'installedPackages': {},
       'runtimeLoadedSourceVerified': False, 'mutationPerformed': False}
for relative in ('helpers/fasta2a_server.py', 'initialize.py', 'agent.py', 'helpers/settings.py'):
    path = Path('/a0') / relative
    if path.is_file() and not path.is_symlink() and path.stat().st_size < 1000000:
        out['sourceHashes'][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
for relative in ('usr/settings.json', 'tmp/settings.json'):
    path = Path('/a0') / relative
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1000000:
        continue
    try:
        settings = json.loads(path.read_text())
        if not isinstance(settings, dict):
            continue
    except (OSError, ValueError):
        continue
    fields = {}
    for model in ('chat', 'utility', 'browser', 'embedding'):
        for suffix in ('provider', 'name', 'api_base'):
            key = model + '_model_' + suffix
            if key in settings:
                fields[key] = endpoint(settings[key]) if suffix == 'api_base' else identifier(settings[key])
    out['settings'].append({'path': relative, 'fields': fields})
for package in ('fasta2a', 'litellm'):
    try:
        out['installedPackages'][package] = identifier(importlib.metadata.version(package))
    except importlib.metadata.PackageNotFoundError:
        out['installedPackages'][package] = None
print(json.dumps(out, sort_keys=True))
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--fingerprint', required=True, help='Independently verified SHA256 SSH host fingerprint')
    parser.add_argument('--container', default='agent-zero-xrev-agent-zero-1')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,120}', args.container):
        parser.error('Invalid container name')
    if not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', args.fingerprint):
        parser.error('Invalid pinned fingerprint')
    if not 1 <= args.port <= 65535:
        parser.error('Invalid SSH port')
    if not sys.stdin.isatty():
        parser.error('Run in an owner-operated terminal for hidden password input')
    import paramiko

    transport = None
    try:
        sock = socket.create_connection((args.host, args.port), timeout=10)
        transport = paramiko.Transport(sock)
        transport.get_security_options().key_types = ('ssh-ed25519',)
        transport.banner_timeout = transport.auth_timeout = 15
        transport.start_client(timeout=15)
        key = transport.get_remote_server_key()
        observed = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
        if not hmac.compare_digest(observed, args.fingerprint):
            raise RuntimeError('SSH host fingerprint mismatch; authentication was not attempted')
        password = getpass.getpass('SSH password (hidden): ')
        try:
            transport.auth_password(args.user, password, fallback=False)
        finally:
            del password
        channel = transport.open_session(timeout=15)
        channel.settimeout(15)
        channel.exec_command('docker exec -i ' + shlex.quote(args.container) + ' python -')
        channel.sendall(CONTAINER_PROBE.encode())
        channel.shutdown_write()
        output = bytearray()
        deadline = time.monotonic() + 45
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('Readback deadline exceeded')
            if channel.recv_ready():
                output.extend(channel.recv(4096))
                if len(output) > 65536:
                    raise RuntimeError('Readback exceeded bounded output limit')
            if channel.recv_stderr_ready():
                channel.recv_stderr(4096)  # Never print unknown remote error content.
            if channel.exit_status_ready() and not channel.recv_ready():
                break
            time.sleep(0.02)
        if channel.recv_exit_status() != 0:
            raise RuntimeError('Agent Zero metadata probe failed')
        result = json.loads(output)
        result['sshHostKeyVerified'] = True
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        if transport is not None:
            transport.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Exception class is sufficient; authentication payloads are never logged.
        print(json.dumps({'ok': False, 'errorType': type(exc).__name__, 'mutationPerformed': False}), file=sys.stderr)
        raise SystemExit(1)
