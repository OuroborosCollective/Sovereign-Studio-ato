from __future__ import annotations

from pathlib import Path


def test_canonical_backend_has_no_trailing_whitespace() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text("utf-8")
    offending = [
        line_number
        for line_number, line in enumerate(source.splitlines(), start=1)
        if line != line.rstrip()
    ]
    assert offending == []
