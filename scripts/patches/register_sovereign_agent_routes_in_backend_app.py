#!/usr/bin/env python3
"""Register neutral Sovereign Agent routes in backend/app.py.

This helper exists because backend/app.py is a large live backend file. The patch
is exact and small: it adds imports, a pooled DB connection helper, and one route
registration call. It intentionally refuses to run if the expected anchors changed.

Usage from repo root:

    python scripts/patches/register_sovereign_agent_routes_in_backend_app.py
    python -m py_compile backend/app.py backend/agent_runtime/routes.py
"""

from __future__ import annotations

from pathlib import Path

APP_PATH = Path("backend/app.py")

IMPORT_SEARCH = """import requests
"""

IMPORT_REPLACE = """import requests

from agent_runtime.routes import register_sovereign_agent_routes
"""

POOL_HELPER_SEARCH = """def query(sql: str, params=None, *, one=False, write=False):
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if write:
                conn.commit()
                return None
            if one:
                return cur.fetchone()
            return cur.fetchall()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
"""

POOL_HELPER_REPLACE = """def query(sql: str, params=None, *, one=False, write=False):
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if write:
                conn.commit()
                return None
            if one:
                return cur.fetchone()
            return cur.fetchall()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


class PooledAgentConnection:
    \"\"\"DB-API compatible connection wrapper for agent_runtime job store.

    The neutral agent runtime owns SQL for sovereign_agent_jobs. This wrapper
    provides a real pooled connection and returns it to the Flask pool on close.
    \"\"\"

    def __init__(self):
        self._pool = get_pool()
        self._conn = self._pool.getconn()
        self._closed = False

    def cursor(self):
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if not self._closed:
            self._pool.putconn(self._conn)
            self._closed = True


def get_agent_runtime_connection() -> PooledAgentConnection:
    return PooledAgentConnection()
"""

REGISTER_SEARCH = """    return decorated
# ── User OpenHands Jobs (Tool Section) ───────────────────────────────────────
"""

REGISTER_REPLACE = """    return decorated


register_sovereign_agent_routes(
    app,
    require_session=require_session,
    get_connection=get_agent_runtime_connection,
)

# ── User OpenHands Jobs (Tool Section) ───────────────────────────────────────
"""


def replace_once(content: str, search: str, replace: str, label: str) -> str:
    count = content.count(search)
    if count != 1:
        raise SystemExit(f"Patch anchor {label!r} expected exactly once, found {count}.")
    return content.replace(search, replace, 1)


def main() -> None:
    content = APP_PATH.read_text(encoding="utf-8")
    content = replace_once(content, IMPORT_SEARCH, IMPORT_REPLACE, "import requests")
    content = replace_once(content, POOL_HELPER_SEARCH, POOL_HELPER_REPLACE, "query helper")
    content = replace_once(content, REGISTER_SEARCH, REGISTER_REPLACE, "require_session route registration")
    APP_PATH.write_text(content, encoding="utf-8")
    print("Registered neutral Sovereign Agent routes in backend/app.py")


if __name__ == "__main__":
    main()
