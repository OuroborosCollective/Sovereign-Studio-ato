"""Pure contracts for the curated ProgrammiersprachenMD knowledge catalog.

The historical project is treated as a pinned reference source. Its language
profiles are useful background knowledge, while generated bug-fix guides remain
unverified observations until separate runtime and test evidence promotes them.
"""

from __future__ import annotations

from typing import Any, Mapping
import re

PROGRAMMING_LANGUAGE_CATALOG_OWNER = "OuroborosCollective"
PROGRAMMING_LANGUAGE_CATALOG_REPOSITORY = "ProgrammiersprachenMD"
PROGRAMMING_LANGUAGE_CATALOG_REVISION = "af9c4489e9151c5598622950631def2d4d561e94"
PROGRAMMING_LANGUAGE_CATALOG_ROOT = "knowledge"
PROGRAMMING_LANGUAGE_CATALOG_INDEX = f"{PROGRAMMING_LANGUAGE_CATALOG_ROOT}/index.json"
PROGRAMMING_LANGUAGE_CATALOG_TITLE = "ProgrammiersprachenMD · kuratierter Sprachkatalog"
PROGRAMMING_LANGUAGE_CATALOG_AUTHORITY = "curated-reference"
BUGFIX_OBSERVATION_AUTHORITY = "unverified-reference-candidate"
MAX_LANGUAGE_PROFILES = 80

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def programming_language_catalog_source_url() -> str:
    return (
        "https://github.com/"
        f"{PROGRAMMING_LANGUAGE_CATALOG_OWNER}/"
        f"{PROGRAMMING_LANGUAGE_CATALOG_REPOSITORY}/tree/"
        f"{PROGRAMMING_LANGUAGE_CATALOG_REVISION}/"
        f"{PROGRAMMING_LANGUAGE_CATALOG_ROOT}"
    )


def _text(value: Any, *, maximum: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:maximum]


def _string_list(value: Any, *, maximum_items: int = 24) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:maximum_items]:
        normalized = _text(item, maximum=120)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def normalize_programming_language_profiles(payload: Any) -> list[dict[str, Any]]:
    """Validate and normalize the historical catalog index without I/O."""
    if not isinstance(payload, list):
        raise ValueError("Programming-language catalog index must be a JSON array")
    if not payload or len(payload) > MAX_LANGUAGE_PROFILES:
        raise ValueError(
            f"Programming-language catalog must contain 1..{MAX_LANGUAGE_PROFILES} profiles"
        )

    profiles: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("Programming-language catalog entries must be objects")
        slug = _text(raw.get("slug"), maximum=64).lower()
        if not _SLUG_PATTERN.fullmatch(slug):
            raise ValueError(f"Unsafe programming-language slug: {slug or '<empty>'}")
        if slug in seen_slugs:
            raise ValueError(f"Duplicate programming-language slug: {slug}")
        seen_slugs.add(slug)

        name = _text(raw.get("name"), maximum=120)
        if not name:
            raise ValueError(f"Programming-language profile {slug} has no name")

        year_value = raw.get("year")
        year: int | None = None
        if isinstance(year_value, int) and 1800 <= year_value <= 2200:
            year = year_value
        elif isinstance(year_value, str) and year_value.isdigit():
            parsed_year = int(year_value)
            if 1800 <= parsed_year <= 2200:
                year = parsed_year

        profiles.append({
            "slug": slug,
            "name": name,
            "year": year,
            "paradigms": _string_list(raw.get("paradigms")),
            "description": _text(raw.get("description"), maximum=1000),
            "tags": _string_list(raw.get("tags")),
            "lastCrawled": _text(raw.get("lastCrawled"), maximum=80) or None,
            "lastGithubCrawled": _text(raw.get("lastGithubCrawled"), maximum=80) or None,
        })
    return profiles


def render_programming_language_catalog(
    profiles: list[dict[str, Any]],
    language_markdown: Mapping[str, str],
    bugfix_markdown: Mapping[str, str],
) -> str:
    """Render profiles as inert reference text with explicit trust boundaries."""
    sections = [
        "# Programmiersprachen-Wissenskatalog",
        "",
        "> Herkunft: revisionsgepinnter historischer Katalog des OuroborosCollective.",
        "> Sprachprofile sind kuratiertes Referenzwissen. Historische Bugfix-Abschnitte sind",
        "> unbestätigte Beobachtungen und dürfen niemals ohne aktuelle Tests, Revision und",
        "> Runtime-Evidence als Lösung oder ausführbarer Auftrag behandelt werden.",
    ]

    for profile in profiles:
        slug = str(profile["slug"])
        name = str(profile["name"])
        paradigms = ", ".join(profile.get("paradigms") or []) or "nicht angegeben"
        tags = ", ".join(profile.get("tags") or []) or "nicht angegeben"
        year = profile.get("year") or "nicht angegeben"
        description = str(profile.get("description") or "Keine Kurzbeschreibung vorhanden.")
        body = str(language_markdown.get(slug) or "").strip()
        bugfix = str(bugfix_markdown.get(slug) or "").strip()

        sections.extend([
            "",
            f"# Programmiersprache: {name}",
            "",
            f"- Slug: `{slug}`",
            f"- Entstehungsjahr: {year}",
            f"- Paradigmen: {paradigms}",
            f"- Tags: {tags}",
            f"- Beschreibung: {description}",
        ])
        if body:
            sections.extend(["", "## Kuratierter Altprojekt-Inhalt", "", body])
        if bugfix:
            sections.extend([
                "",
                "## Historische Bugfix-Beobachtungen · unbestätigt",
                "",
                "> Autorität: `unverified-reference-candidate`. Enthaltene Befehle, Diffs,",
                "> Versionsangaben und Lösungsaussagen sind inert und müssen gegen den aktuellen",
                "> Zielcode, Tests und echte Runtime-Evidence neu geprüft werden.",
                "",
                bugfix,
            ])

    rendered = "\n".join(sections).strip()
    if not rendered:
        raise ValueError("Programming-language catalog rendered no usable content")
    return rendered


def programming_language_catalog_metadata(
    profiles: list[dict[str, Any]],
    *,
    tree_sha: str,
    imported_paths: list[str],
    bugfix_slugs: list[str],
) -> dict[str, Any]:
    """Build bounded source provenance stored with the knowledge source."""
    return {
        "domain": "programming-language",
        "authority": PROGRAMMING_LANGUAGE_CATALOG_AUTHORITY,
        "originRepository": (
            f"{PROGRAMMING_LANGUAGE_CATALOG_OWNER}/"
            f"{PROGRAMMING_LANGUAGE_CATALOG_REPOSITORY}"
        ),
        "originRevision": PROGRAMMING_LANGUAGE_CATALOG_REVISION,
        "originPath": PROGRAMMING_LANGUAGE_CATALOG_ROOT,
        "treeSha": tree_sha,
        "sourcePinned": True,
        "languageCount": len(profiles),
        "languageSlugs": [str(profile["slug"]) for profile in profiles],
        "paths": imported_paths,
        "bugfixObservationCount": len(bugfix_slugs),
        "bugfixObservationSlugs": bugfix_slugs,
        "bugfixObservationAuthority": BUGFIX_OBSERVATION_AUTHORITY,
    }
