"""Minimal LangChain-style adapter for the REST generic dispatcher.

Use this pattern in agent frameworks that can call Python functions.
"""
from __future__ import annotations
import os
import requests

BASE_URL = os.getenv("TOOLCHAIN_BASE_URL", "http://localhost:8000/api")
TOOLCHAIN_API_KEY = os.getenv("TOOLCHAIN_API_KEY", "")

def call_sovereign_tool(name: str, **kwargs):
    headers = {"Content-Type": "application/json"}
    if TOOLCHAIN_API_KEY:
        headers["X-Toolchain-Key"] = TOOLCHAIN_API_KEY
    r = requests.post(f"{BASE_URL}/v1/tools/{name}", json={"args": kwargs}, headers=headers, timeout=90)
    r.raise_for_status()
    return r.json()

# Example:
# call_sovereign_tool("plan_sandbox_commands", goal="verify")
