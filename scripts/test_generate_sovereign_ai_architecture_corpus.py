from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_sovereign_ai_architecture_corpus.py")
SPEC = importlib.util.spec_from_file_location("sovereign_ai_architecture_corpus", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
corpus = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = corpus
SPEC.loader.exec_module(corpus)


def test_revision_has_required_architecture_coverage() -> None:
    paths = corpus.source_paths(corpus.DEFAULT_REVISION)
    assert len(paths) >= corpus.MINIMUM_FILE_COUNT
    assert len(paths) == 1643
    assert paths == sorted(paths)


def test_sensitive_assignment_is_redacted() -> None:
    key_name = "".join(["pass", "word"])
    hidden = "value-" + ("x" * 30)
    rendered, count = corpus.redact_text(f'{key_name}="{hidden}"\nvisible="ok"\n')
    assert count >= 1
    assert hidden not in rendered
    assert "<REDACTED:" in rendered
    assert 'visible="ok"' in rendered


def test_null_bytes_are_base64_encoded() -> None:
    rendered, encoding = corpus.decode_blob(b"alpha\0omega")
    assert encoding == "base64"
    assert "\0" not in rendered
