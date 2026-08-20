"""Unit tests for Passkey Origin security validation in security_runtime."""

from __future__ import annotations

import pytest
from flask import Flask

import security_runtime as sr


@pytest.fixture
def app():
    app = Flask("test_security_runtime_origin")
    app.config["TESTING"] = True
    return app


def test_request_origin_valid_allowed_origin(app):
    """Test that a configured, allowed origin is returned successfully."""
    valid_origin = sr.PASSKEY_ALLOWED_ORIGINS[0]
    with app.test_request_context("/", headers={"Origin": valid_origin}):
        origin = sr._request_origin()
        assert origin == valid_origin


def test_request_origin_missing_header_raises_value_error(app):
    """Test that missing or empty Origin header raises ValueError."""
    with app.test_request_context("/", headers={}):
        with pytest.raises(ValueError, match="Origin header is required"):
            sr._request_origin()

    with app.test_request_context("/", headers={"Origin": ""}):
        with pytest.raises(ValueError, match="Origin header is required"):
            sr._request_origin()

    with app.test_request_context("/", headers={"Origin": "   "}):
        with pytest.raises(ValueError, match="Origin header is required"):
            sr._request_origin()


def test_request_origin_unauthorized_origin_raises_value_error(app):
    """Test that an untrusted or illegal Origin header raises ValueError."""
    with app.test_request_context("/", headers={"Origin": "https://attacker.com"}):
        with pytest.raises(ValueError, match="Request origin is not allowed"):
            sr._request_origin()
