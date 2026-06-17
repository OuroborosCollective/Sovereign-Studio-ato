# Remote Memory Security Checklist

This checklist defines the production hardening rules for Sovereign Studio Remote Memory.

## Production gateway

- Use HTTPS in production.
- Keep direct vector database, object storage and admin UI ports away from public browser clients.
- Browser clients must talk only to the Sovereign Memory Gateway.
- Keep CORS limited to trusted application origins.
- Keep rate limiting enabled.
- Keep request body size limits enabled.
- Keep response size limits enabled.
- Keep audit logging summary-only.

## Contributor scope

Remote Memory uses two scopes:

- `user-submitted-summary`: per-contributor submitted summaries.
- `shared-derived-pattern`: shared pattern output generated from accepted aggregate learning.

Contributor cleanup may target only:

- same workspace;
- same collection;
- same contributor id;
- `user-submitted-summary` scope.

Contributor cleanup must preserve:

- `shared-derived-pattern`;
- aggregate pattern updates;
- other contributor ids;
- other workspaces;
- other collections.

## Client payload rules

The client-side builder must keep these rules:

- summary-only payloads;
- no raw source files;
- no raw repository snapshots;
- no persisted session access strings;
- explicit contributor id;
- explicit collection name;
- explicit workspace id;
- explicit consent flag;
- soft-fail on invalid config.

## Gateway endpoint expectations

Required endpoints:

```txt
GET  /health
GET  /api/sovereign-memory/monitoring
POST /api/sovereign-memory/sync
POST /api/sovereign-memory/search
GET  /api/sovereign-memory/pull-updates
POST /api/sovereign-memory/delete-user-data
```

The user-facing product may call the last flow "Bereinigen", "Remove" or "Revoke". The endpoint name can remain stable for compatibility.

## Monitoring expectations

The monitoring endpoint should expose only operational status:

- service name;
- version;
- uptime;
- memory usage;
- inbound request counters;
- blocked request counters;
- filtered request counters;
- passed request counters;
- vector gateway connectivity state.

It must not expose stored pattern content.

## Release gate

Remote Memory production changes are healthy only if:

- local runtime tests pass;
- contributor scope tests pass;
- shared-pattern preservation tests pass;
- test lanes stay separated;
- UI wording remains clear about what is cleaned and what is retained.
