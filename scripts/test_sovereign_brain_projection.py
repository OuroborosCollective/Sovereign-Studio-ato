import json
import tempfile
import unittest
from pathlib import Path

from scripts.sovereign_brain_projection import (
    SCHEMA_VERSION,
    TRUTH_CLASS,
    build_manifest,
    git_blob_sha1,
    validate,
)


PAGE_TEXT = """# Test page

schema: sovereign.brain-projection.v1
truth_class: DERIVED_PROJECTION
runtime_verified: false

## compiled_truth

This is a projection only.

## timeline

History remains in external receipts.
"""


class SovereignBrainProjectionTests(unittest.TestCase):
    def test_git_blob_sha_matches_known_git_vector(self):
        self.assertEqual(
            git_blob_sha1(b"hello\n"),
            "ce013625030ba8dba906f756967f9e9ca394464a",
        )

    def test_manifest_is_deterministic_and_projection_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("source\n", encoding="utf-8")
            (root / "BRAIN.md").write_text(PAGE_TEXT, encoding="utf-8")

            first = build_manifest(
                root,
                source_paths=("source.txt",),
                page_paths=("BRAIN.md",),
            )
            second = build_manifest(
                root,
                source_paths=("source.txt",),
                page_paths=("BRAIN.md",),
            )

            self.assertEqual(first, second)
            self.assertEqual(first["schemaVersion"], SCHEMA_VERSION)
            self.assertEqual(first["truthClass"], TRUTH_CLASS)
            self.assertFalse(first["runtimeVerified"])
            self.assertTrue(
                first["truthBoundary"]["continuityGithubWorkflowAdvisoryOnly"]
            )

    def test_current_repository_manifest_matches_tracked_projection_inputs(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(validate(root), [])

    def test_validation_detects_source_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brain").mkdir()
            (root / "source.txt").write_text("source\n", encoding="utf-8")
            (root / "BRAIN.md").write_text(PAGE_TEXT, encoding="utf-8")

            manifest = build_manifest(
                root,
                source_paths=("source.txt",),
                page_paths=("BRAIN.md",),
            )
            (root / "brain" / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            (root / "source.txt").write_text("changed\n", encoding="utf-8")
            errors = validate(root)
            self.assertIn("GIT_BLOB_HASH_MISMATCH:source.txt", errors)
            self.assertIn("SHA256_MISMATCH:source.txt", errors)

    def test_validation_rejects_runtime_claim_in_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brain").mkdir()
            (root / "source.txt").write_text("source\n", encoding="utf-8")
            (root / "BRAIN.md").write_text(
                PAGE_TEXT.replace("runtime_verified: false", "runtime_verified: true"),
                encoding="utf-8",
            )
            manifest = build_manifest(
                root,
                source_paths=("source.txt",),
                page_paths=("BRAIN.md",),
            )
            (root / "brain" / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            errors = validate(root)
            self.assertTrue(
                any(error.startswith("PAGE_FORBIDDEN_TRUTH_CLAIM:BRAIN.md") for error in errors)
            )


if __name__ == "__main__":
    unittest.main()
