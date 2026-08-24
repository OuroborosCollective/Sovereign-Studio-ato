#!/usr/bin/env python3
"""Small local client used only by the controlled host-side worker canary."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, help="JSON request object")
    arguments = parser.parse_args()
    try:
        request = json.loads(arguments.request)
    except json.JSONDecodeError:
        return 64
    if not isinstance(request, dict):
        return 64
    payload = json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path = os.environ.get("DESKTOP_CONTROL_SOCKET", "/run/desktop-control/worker.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(path)
        connection.sendall(payload)
        response = connection.recv(8192)
    sys.stdout.write(response.decode("utf-8") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
