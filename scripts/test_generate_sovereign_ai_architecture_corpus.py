from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

MODULE_PATH = Path(__file__).with_name("generate_sovereign_ai_architecture_corpus.py")
SPEC = importlib.util.spec_from_file_location("sovereign_ai_architecture_corpus", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
corpus = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = corpus
SPEC.loader.exec_module(corpus)


def test_exact_revision_contains_expected_mapped_text_file_count() -> None:
    paths = corpus.tracked_mapped_paths(corpus.DEFAULT_REVISION)
    suffix_counts = Counter(PurePosixPath(path).suffix.lower() for path in paths)
    minimum_count = int(corpus.EXPECTED_FILE_COUNT * corpus.MINIMUM_ARCHITECTURE_COVERAGE)
    if len(paths) < minimum_count:
        raise AssertionError(json.dumps(dict(sorted(suffix_counts.items())), sort_keys=True))
    assert len(paths) == 1643
    assert minimum_count >= 1560
    assert paths == sorted(paths)
    assert "README.md" in paths
    assert "scripts/sovereign-backend/app.py" in paths


def test_sensitive_assignment_is_redacted_without_returning_value() -> None:
    key_name = "".join(["pass", "word"])
    hidden_value = "value-" + ("x" * 30)
    source = f'{key_name}="{hidden_value}"\nnormal = "visible"\n'
    rendered, count = corpus.redact_text(source)
    assert count >= 1
    assert hidden_value not in rendered
    assert "<REDACTED:" in rendered
    assert 'normal = "visible"' in rendered


def test_tree_and_record_delimiters_are_deterministic() -> None:
    blob = b"hello\n"
    digest = corpus.sha256_bytes(blob)
    record = corpus.FileRecord(
        index=1,
        path="docs/example.md",
        language="markdown",
        original_bytes=blob,
        original_sha256=digest,
        rendered_content="hello\n",
        rendered_sha256=digest,
        redaction_count=0,
        encoding="utf-8",
    )
    document = corpus.render_document(corpus.DEFAULT_REVISION, [record])
    corpus.validate_document(document, [record])
    assert "Sovereign-Studio-ato/" in document
    assert "docs/" in document
    assert "example.md" in document
    assert document.count("<!-- SOVEREIGN_FILE_BEGIN ") == 1
    assert document.count("<!-- SOVEREIGN_FILE_END -->") == 1
