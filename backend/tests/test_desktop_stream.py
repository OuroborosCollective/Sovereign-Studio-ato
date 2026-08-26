from __future__ import annotations

import os

import pytest

from backend.agent_runtime.desktop_stream import (
    DesktopStreamError,
    desktop_worker_host,
    issue_stream_ticket,
    verify_stream_ticket,
)


def test_stream_ticket_binds_job_activation_and_session(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_DESKTOP_STREAM_TICKET_SECRET", "s" * 64)
    ticket = issue_stream_ticket(
        user_id="owner-user",
        job_id="job-stream123",
        activation_id="a" * 64,
        session_binding_hash="b" * 64,
        ttl_seconds=90,
    )
    payload = verify_stream_ticket(ticket["ticket"], job_id="job-stream123")
    assert payload["activation"] == "a" * 64
    assert payload["session"] == "b" * 64
    assert payload["uid"] == "owner-user"


def test_stream_ticket_rejects_other_job(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_DESKTOP_STREAM_TICKET_SECRET", "s" * 64)
    ticket = issue_stream_ticket(
        user_id="owner-user",
        job_id="job-stream123",
        activation_id="a" * 64,
        session_binding_hash="b" * 64,
    )
    with pytest.raises(DesktopStreamError, match="binding"):
        verify_stream_ticket(ticket["ticket"], job_id="job-other123")


def test_worker_host_is_deterministic_and_session_bound():
    assert desktop_worker_host("c" * 64) == "sovereign-desktop-" + "c" * 20


def test_stream_ticket_requires_real_secret(monkeypatch):
    monkeypatch.delenv("SOVEREIGN_DESKTOP_STREAM_TICKET_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(DesktopStreamError, match="secret"):
        issue_stream_ticket(
            user_id="owner-user",
            job_id="job-stream123",
            activation_id="a" * 64,
            session_binding_hash="b" * 64,
        )
