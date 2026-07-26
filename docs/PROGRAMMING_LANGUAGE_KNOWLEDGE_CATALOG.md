# ProgrammiersprachenMD integration

## Purpose

Sovereign Studio ATO reuses the useful domain knowledge from the historical
`OuroborosCollective/ProgrammiersprachenMD` project without deploying its old
Replit application, Express server, file-backed runtime, or crawler routes.

The integration imports one immutable historical source revision:

- repository: `OuroborosCollective/ProgrammiersprachenMD`
- revision: `af9c4489e9151c5598622950631def2d4d561e94`
- source root: `knowledge`
- authority: `curated-reference`

The pinned commit is part of the source identity. A moving branch such as
`main` is deliberately not used.

## Runtime path

The authenticated user action calls:

`POST /api/knowledge/catalogs/programming-languages/import`

The authenticated admin equivalent is:

`POST /api/admin/knowledge/catalogs/programming-languages/import`

The backend then:

1. resolves the exact commit through the GitHub API;
2. verifies that GitHub returned the requested 40-character revision;
3. resolves and validates the commit tree identity;
4. stops if the recursive tree is truncated;
5. reads and validates `knowledge/index.json`;
6. accepts only bounded, unique, path-safe language slugs;
7. imports matching `knowledge/languages/<slug>.md` files;
8. imports matching `knowledge/bugfixes/<slug>.md` files when present;
9. renders a single inert reference document with explicit trust boundaries;
10. hashes, chunks, embeds, stores, deduplicates, and indexes it through the
    existing PostgreSQL/pgvector knowledge pipeline.

No imported command, setup script, patch, or diff is executed.

## Trust model

Language profiles are curated reference knowledge. They may assist stack
selection, explanation, code review, or generation, but remain external source
material.

Historical bug-fix guides are stored with the authority:

`unverified-reference-candidate`

A commit message containing words such as `fix`, `resolve`, or `patch` is not
proof of a reusable solution. Promotion into proven learning requires separate
current evidence, such as a reproducible failing test, a passing repaired test,
exact target revision, and runtime readback.

Reference knowledge and evidence-derived agent experience remain separate.

## Stored provenance

The knowledge source metadata records:

- origin repository;
- exact origin revision;
- origin path;
- commit SHA and tree SHA;
- imported paths;
- language slugs and language count;
- bug-fix observation slugs and count;
- reference and bug-fix authority values;
- source-pinned state.

The normal knowledge-source SHA-256 remains the content identity and preserves
idempotent duplicate handling per user.

## UI

The Knowledge Library exposes a dedicated `Sprachkatalog übernehmen` action.
Existing sources display language-profile count, unverified bug-fix observation
count, and the short origin revision when the corresponding metadata exists.

## Deliberately excluded legacy surfaces

The following historical components are not copied into the live architecture:

- Replit deployment configuration;
- the standalone Express API;
- the standalone React application;
- JSON and Markdown files as a mutable runtime database;
- direct crawler writes into source files;
- automatic setup-script execution;
- automatic promotion of public GitHub fixes into proven learning;
- a new Docker container or network.

This keeps one authoritative knowledge runtime and avoids parallel state,
parallel authentication, and parallel operational ownership.

## Required release evidence

A release claim requires at minimum:

- backend and deployment mirrors are byte-identical;
- catalog normalization tests pass;
- exact revision and tree checks pass;
- truncated trees fail closed;
- unsafe and duplicate slugs fail closed;
- bug-fix observations remain explicitly unverified;
- frontend API and action tests pass;
- repository CI is bound to the PR head revision;
- deployment and live catalog import are not claimed until immutable backend
  image and runtime canary evidence are available.
