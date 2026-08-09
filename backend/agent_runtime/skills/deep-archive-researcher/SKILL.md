---
name: deep-archive-researcher
description: "Evidence-first wide research, validation and archival workflow for complex historical, technical, legal or identity research. Separates primary evidence, claims, speculation and refutation and adapts external research/archive capabilities to the tools actually available at runtime."
---

# Deep Archive Researcher

Use this skill for systematic broad research where provenance, evidence level, chronology and claim separation matter.

## Sovereign truth boundary

- Never turn an unavailable source or tool into invented evidence.
- A label such as `green`, `verified`, `success` or `error` is not itself proof. Trace the result to its originating evidence before accepting the classification.
- No mocks, fake snapshots, synthetic citations or stub systems in a truth path.
- Preserve source URL/identifier, retrieval time when available, document/event time when known, and the distinction between source text and inference.
- Missing or uninspectable evidence remains unverified; do not silently promote it.
- Keep research evidence separate from runtime/deployment evidence. This skill does not prove repository or production runtime state.

## Capability adaptation

The workflow is capability-based, not coupled to literal tool names from another host.

For each run, map these logical capabilities to tools actually available in the current environment:

1. `archive_search` — search an existing Notion/knowledge/archive store.
2. `archive_fetch` — fetch schema, pages, databases or stored evidence.
3. `wide_search` — parallel/batched public-source discovery.
4. `source_fetch` — retrieve primary or secondary source content.
5. `archive_write` — create structured archive/database entries.
6. `document_fallback` — persist a structured Markdown/report artifact if archive writing is unavailable.
7. `formal_analysis` — optional quantitative/formal verification (for example Wolfram) when the claim is actually amenable to it.

Never claim a capability exists until the current runtime exposes it. If a preferred capability is absent, continue with the strongest available evidence-preserving fallback rather than fabricating completion.

## Core workflow

### 1. Archive inspection

When an archive is part of the assignment:

- Search for the target archive before creating new structures.
- Fetch the relevant database/page schema.
- Identify required fields, evidence levels, identifiers and duplicate keys.
- Read existing claims relevant to the research question before inserting new ones.

### 2. Wide research

Split the question into at least 5-8 useful dimensions when the topic supports that breadth. Typical dimensions include:

- Primary sources and earliest documents
- Communication history: forums, mailing lists, email, interviews
- Technical genesis and infrastructure
- Identities, organizations and involved people
- Legal records and official findings
- Geographic and chronological patterns
- Contemporary reporting and later retrospectives
- Contradictions, refutations and unresolved claims

Search dimensions independently enough to avoid one source family laundering a claim through repetition.

Prefer primary/original sources first, then independently archived copies, then independent corroboration. Use secondary reporting for discovery and context, not to silently upgrade an unsupported claim.

### 3. Evidence normalization

For every material claim record, capture where available:

- `claim_id`
- `claim`
- `subject`
- `source_title`
- `source_locator`
- `source_type`
- `published_or_event_time`
- `retrieved_at`
- `location`
- `evidence_level`
- `supports_or_refutes`
- `independent_of`
- `notes`
- `open_questions`

Keep quotations short and exact. Prefer paraphrase plus a precise source locator.

### 4. Evidence levels

Use exactly these semantic levels unless the target archive defines a stricter compatible vocabulary:

1. **Primär belegt** — original text, original code, signed message, official record, direct artifact.
2. **Unabhängig archiviert** — independently timestamped or otherwise traceable archive copy of source material.
3. **Unabhängig bestätigt** — multiple genuinely independent reliable sources corroborate the material fact.
4. **Zeitgenössisch berichtet** — credible contemporary reporting without accessible primary evidence.
5. **Behauptet** — attributed assertion by a person or organization without sufficient corroboration.
6. **Spekulativ** — inference, pattern or hypothesis without proof.
7. **Widerlegt** — contradicted by stronger evidence or an authoritative finding; retain the original claim and link the refutation rather than deleting history.

Do not convert popularity, repetition, model confidence or stylistic similarity into a higher evidence level.

### 5. Duplicate and independence checks

Before archive insertion:

- Normalize source locators and stable identifiers.
- Detect exact and near-duplicate claims.
- Treat mirrors, syndicated articles and articles quoting the same underlying report as one evidence lineage unless independence is proven.
- Preserve conflicting records and connect them explicitly.

### 6. Archival write

Primary path: write structured records into the configured archive/database using its real schema.

Fallback path: if archive writing/authentication is unavailable, persist a structured Markdown research report and a machine-readable intermediate dataset when the available runtime permits file output. Do not report the archive as updated when only the fallback artifact exists.

## Research report structure

A fallback report should contain:

1. Primary sources and documentation
2. Communication history and network relationships
3. Technical details and infrastructure
4. Identities, entities and claims
5. Forensics and verification
6. Claims & Evidence Ledger
7. Contradictions/refutations
8. Open questions and next search paths

## Efficiency and failure handling

- Batch independent searches when possible.
- Avoid repeatedly retrying an authentication path that has already produced a persistent authorization failure.
- Preserve intermediate structured results before expensive follow-up work when file persistence is available.
- If a source is inaccessible, record that limitation and seek an independent archive or primary equivalent.
- Never cite a search-result snippet as though the underlying document was inspected when it was not.

## Sovereign Studio repository boundary

When this skill is used inside Sovereign Studio development:

- Follow the repository's isolated-workspace, exact-patch, evidence and Draft-PR rules.
- Repository architecture sensors are orientation until backed by readback/evidence.
- Do not confuse this research skill's evidence ledger with deployment, revision, continuity or runtime truth ledgers.
- This skill must not introduce a second LLM routing truth path. Existing provider/runtime policy remains authoritative.
