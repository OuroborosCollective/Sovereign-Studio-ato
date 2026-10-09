"""Regression checks for the real static site validation path (stdlib only)."""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-public-site.py"
spec = importlib.util.spec_from_file_location("verify_public_site", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("missing actual production site validator")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicSiteContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / "site"
        shutil.copytree(ROOT / "public-site", self.site)

    def errors(self, release: bool = False) -> list[str]:
        return module.inspect_site(self.site, release=release)

    def test_real_site_preview_passes(self) -> None:
        self.assertEqual([], self.errors())

    def test_publication_fails_closed_without_complete_legal_content(self) -> None:
        legal = self.site / "impressum.html"
        legal.write_text(legal.read_text(encoding="utf-8") + "\n<!-- PUBLICATION_BLOCKER -->", encoding="utf-8")
        self.assertTrue(any("publication BLOCKED" in err for err in self.errors(release=True)))

    def test_unresolved_anchor_fails(self) -> None:
        source = self.site / "index.html"
        text = source.read_text(encoding="utf-8").replace('href="#architektur"', 'href="#nonexistent-test-anchor"', 1)
        source.write_text(text, encoding="utf-8")
        self.assertTrue(any("unresolved anchor" in err for err in self.errors()))

    def test_remote_script_fails(self) -> None:
        source = self.site / "index.html"
        source.write_text(source.read_text(encoding="utf-8") + '<script src="https://example.org/x.js"></script>', encoding="utf-8")
        self.assertTrue(any("unexpected executable/embed tag" in err for err in self.errors()))

    def test_missing_css_fails(self) -> None:
        (self.site / "assets" / "site.css").unlink()
        self.assertTrue(any("missing or empty required file" in err for err in self.errors()))

    def test_external_blank_target_requires_safe_rel(self) -> None:
        source = self.site / "index.html"
        text = source.read_text(encoding="utf-8").replace('target="_blank" rel="noopener noreferrer"', 'target="_blank"', 1)
        source.write_text(text, encoding="utf-8")
        self.assertTrue(any("target=_blank missing noopener noreferrer" in err for err in self.errors()))

    def test_published_page_must_remove_noindex(self) -> None:
        legal_files = ("impressum.html", "datenschutz.html")
        for filename in legal_files:
            path = self.site / filename
            text = path.read_text(encoding="utf-8").replace("PUBLICATION_BLOCKER", "").replace("PFLICHTANGABE FEHLT", "ERGÄNZT").replace("vor Veröffentlichung", "nach Prüfung").replace('content="noindex, nofollow"', 'content="index, follow"')
            path.write_text(text, encoding="utf-8")
        self.assertTrue(any("release still has noindex" in err for err in self.errors(release=True)))


if __name__ == "__main__":
    unittest.main()
