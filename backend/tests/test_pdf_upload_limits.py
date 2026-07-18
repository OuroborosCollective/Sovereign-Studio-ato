from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

flask_stub = ModuleType("flask")
flask_stub.jsonify = lambda value=None, **kwargs: value if value is not None else kwargs
flask_stub.request = SimpleNamespace()
sys.modules.setdefault("flask", flask_stub)
psycopg2_stub = ModuleType("psycopg2")
psycopg2_extras_stub = ModuleType("psycopg2.extras")
psycopg2_stub.extras = psycopg2_extras_stub
sys.modules.setdefault("psycopg2", psycopg2_stub)
sys.modules.setdefault("psycopg2.extras", psycopg2_extras_stub)

import knowledge_library


class SizedPayload:
    def __init__(self, size: int) -> None:
        self.size = size

    def __len__(self) -> int:
        return self.size


def test_pdf_upload_limit_is_exactly_33_mib(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        knowledge_library,
        "_pdf_document",
        lambda filename, payload: knowledge_library.KnowledgeDocument(
            source_type="pdf",
            title=filename,
            text="verified",
            source_url=None,
            metadata={"bytes": len(payload)},
        ),
    )

    maximum = knowledge_library.upload_document(
        "manual.pdf",
        SizedPayload(33 * 1024 * 1024),
    )
    assert maximum.metadata["bytes"] == 33 * 1024 * 1024
    with pytest.raises(ValueError, match="33 MB"):
        knowledge_library.upload_document(
            "manual.pdf",
            SizedPayload((33 * 1024 * 1024) + 1),
        )


def test_non_pdf_knowledge_upload_limit_remains_12_mib() -> None:
    assert knowledge_library.upload_limit_bytes("manual.txt") == 12 * 1024 * 1024
    with pytest.raises(ValueError, match="12 MB"):
        knowledge_library.upload_document(
            "manual.txt",
            SizedPayload((12 * 1024 * 1024) + 1),
        )
