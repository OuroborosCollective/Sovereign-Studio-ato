from __future__ import annotations

import fcntl
import os
from pathlib import Path
import sqlite3
import threading

import pytest

import neuro_teaching_tools as tools


def test_readonly_connection_waits_for_first_initializer_file_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "neuromorphic-runtime.sqlite3"
    sqlite3.connect(database).close()

    descriptor = os.open(database, os.O_RDWR)
    original_flock = fcntl.flock
    original_flock(descriptor, fcntl.LOCK_EX)

    shared_lock_attempted = threading.Event()
    finished = threading.Event()
    observed: dict[str, int] = {}
    failures: list[BaseException] = []

    def tracked_flock(file_descriptor: int, operation: int) -> None:
        if operation == fcntl.LOCK_SH:
            shared_lock_attempted.set()
        original_flock(file_descriptor, operation)

    monkeypatch.setattr(tools.fcntl, "flock", tracked_flock)

    def reader() -> None:
        try:
            with tools._readonly_connection(database) as connection:
                observed["userVersion"] = int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                )
                observed["markerCount"] = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM sqlite_master "
                        "WHERE type='table' AND name='initialization_marker'"
                    ).fetchone()[0]
                )
        except BaseException as exc:  # surfaced in the main test thread below
            failures.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        assert shared_lock_attempted.wait(2), "reader never attempted the shared initialization lock"
        assert finished.is_set() is False, "reader bypassed the exclusive first-initializer lock"

        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE initialization_marker(value INTEGER NOT NULL)")
            connection.execute("PRAGMA user_version=1")
            connection.commit()
    finally:
        original_flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    assert finished.wait(2), "reader did not resume after initialization lock release"
    thread.join(timeout=2)
    assert failures == []
    assert observed == {"userVersion": 1, "markerCount": 1}
