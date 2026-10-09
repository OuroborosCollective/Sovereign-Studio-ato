#!/usr/bin/env python3
"""Validate the actual static Sovereign marketing site before preview or publication.

Only stdlib; no external calls, generated statuses or client-side build dependency.
A release requires completed legal disclosure and explicit removal of its blockers.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


BLOCKER = "PUBLICATION_BLOCKER"
REQUIRED_FILES = ("index.html", "impressum.html", "datenschutz.html", "assets/site.css")


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, dict[str, str]]] = []
        self.ids: set[str] = set()
        self.errors: list[str] = []
        self.has_lang = False
        self.has_viewport = False
        self.has_title = False
        self.in_title = False
        self.forbidden_tags = {"script", "iframe", "form", "object", "embed"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag in self.forbidden_tags:
            self.errors.append(f"unexpected executable/embed tag: {tag}")
        if tag == "html":
            self.has_lang = data.get("lang") == "de"
        if tag == "title":
            self.in_title = True
        if tag == "meta" and data.get("name", "").lower() == "viewport":
            self.has_viewport = True
        if "id" in data:
            if data["id"] in self.ids:
                self.errors.append(f"duplicate element id: {data['id']}")
            self.ids.add(data["id"])
        if tag in ("a", "link", "img"):
            url = data.get("href", "") if tag != "img" else data.get("src", "")
            if url:
                self.links.append((tag, {"url": url, **data}))

    def handle_data(self, data: str) -> None:
        if self.in_title and data.strip():
            self.has_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False


def inspect_site(root: Path, *, release: bool) -> list[str]:
    errors: list[str] = []
    root = root.resolve()

    for path in REQUIRED_FILES:
        file = root / path
        if not file.is_file() or file.stat().st_size == 0:
            errors.append(f"missing or empty required file: {path}")
    if errors:
        return errors

    css = (root / "assets/site.css").read_text(encoding="utf-8")
    if "@import" in css or "url(" in css:
        errors.append("external CSS imports/resources are not allowed without privacy review")

    documents: dict[str, SiteParser] = {}
    raw_documents: dict[str, str] = {}
    for file in sorted(root.glob("*.html")):
        text = file.read_text(encoding="utf-8")
        parser = SiteParser()
        parser.feed(text)
        parser.close()
        relative = file.relative_to(root).as_posix()
        documents[relative] = parser
        raw_documents[relative] = text
        errors.extend(f"{relative}: {error}" for error in parser.errors)
        for required, present in (("lang=de", parser.has_lang), ("viewport", parser.has_viewport), ("title", parser.has_title)):
            if not present:
                errors.append(f"{relative}: missing {required}")

    for source, parser in documents.items():
        for tag, attrs in parser.links:
            target = attrs["url"]
            parsed = urlsplit(target)
            if parsed.scheme in ("https", "http"):
                if parsed.scheme != "https":
                    errors.append(f"{source}: insecure outbound link {target}")
                if tag == "a" and attrs.get("target") == "_blank":
                    rel = set(attrs.get("rel", "").split())
                    if not {"noopener", "noreferrer"} <= rel:
                        errors.append(f"{source}: target=_blank missing noopener noreferrer: {target}")
                if tag in ("img", "link"):
                    errors.append(f"{source}: remote embedded resource forbidden: {target}")
                continue
            if parsed.scheme or parsed.netloc or target.startswith("//"):
                errors.append(f"{source}: unsupported URL scheme: {target}")
                continue
            if target.startswith(("mailto:", "tel:", "javascript:")):
                errors.append(f"{source}: unsupported URL scheme: {target}")
                continue
            referenced = (root / source).parent / parsed.path if parsed.path else root / source
            resolved = referenced.resolve()
            if not resolved.is_relative_to(root):
                errors.append(f"{source}: path escapes publish root: {target}")
                continue
            if not resolved.exists():
                errors.append(f"{source}: missing local target: {target}")
                continue
            if parsed.fragment and resolved.suffix == ".html":
                relative = resolved.relative_to(root).as_posix()
                if relative in documents and parsed.fragment not in documents[relative].ids:
                    errors.append(f"{source}: unresolved anchor {target}")

    for filename in ("impressum.html", "datenschutz.html"):
        text = raw_documents.get(filename, "")
        if release and (BLOCKER in text or "PFLICHTANGABE FEHLT" in text or "vor veröffentlichung" in text.lower()):
            errors.append(f"{filename}: mandatory legal content is incomplete; publication BLOCKED")
    index = raw_documents.get("index.html", "")
    for target in ("impressum.html", "datenschutz.html", "https://github.com/OuroborosCollective/Sovereign-Studio-ato"):
        if target not in index:
            errors.append(f"index.html: mandatory site or evidence reference missing: {target}")
    if release:
        for filename, text in raw_documents.items():
            if 'content="noindex' in text:
                errors.append(f"{filename}: release still has noindex directive")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="public-site")
    parser.add_argument("--mode", choices=("preview", "release"), default="preview")
    args = parser.parse_args()
    errors = inspect_site(Path(args.root), release=args.mode == "release")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"SITE_VALIDATION_FAILED mode={args.mode} count={len(errors)}")
        return 1
    print(f"SITE_VALIDATION_OK mode={args.mode} pages={len(list(Path(args.root).glob('*.html')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
