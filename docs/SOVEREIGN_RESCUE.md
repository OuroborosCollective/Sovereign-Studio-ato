# Sovereign Rescue

Sovereign Rescue is the bounded freemium repair path for repositories that fail
in one of three v1 families:

1. GitHub Actions and CI
2. Docker Compose and containers
3. PostgreSQL migrations and schema

The user-facing promise is:

> Deine App ist kaputt. Sovereign findet die Ursache, repariert sie sicher und
> beweist, dass sie wieder funktioniert.

## User journey

1. Sign in and provide a canonical GitHub repository URL, base branch and error
   evidence. A private repository may use an ephemeral fine-grained GitHub token.
   The token is sent only to the authenticated backend request and is not stored
   or returned.
2. Select a failure family or let Rescue classify the evidence.
3. Run the free diagnosis. The backend resolves the branch through GitHub and
   binds the report to the returned 40-character commit SHA. The diagnosis
   classifies the family, affected paths, risk and proposal without cloning or
   mutating the repository.
4. Review the Sovereign Outcome Contract.
5. Start one Repair Pack. The backend verifies a real purchase receipt or a
   privileged internal entitlement, locks the account, reserves the pack once,
   writes the append-only credit ledger and records the idempotency key.
6. The existing `free_single_agent` execution profile uses the verified direct
   FreeLLM/Revolver route. It clones only the diagnosed revision into the
   isolated Code-Server workspace, applies a bounded repair and records changed
   files, diff and tests.
7. The existing evidence gate prepares and creates a Draft PR. Rescue-reserved
   jobs do not receive the legacy Draft-PR credit charge a second time.
8. The ProofPack reads the real Draft PR and check runs from GitHub. It is ready
   only when the check-run head SHA equals the Draft PR head, all required
   evidence is present and CI is green.

## Freemium and paid boundary

Free diagnosis:

- resolves the exact repository revision;
- classifies only the three supported v1 families;
- returns affected paths, risk, proposal and Outcome Contract;
- redacts secret-shaped material;
- performs no repository write, clone, branch, commit, PR or credit mutation.

Paid Repair Pack:

- requires `resolve_paid_execution_entitlement` to confirm a joined,
  completed purchase and receipt, or a configured privileged identity;
- costs 10 existing Sovereign credits for non-privileged users;
- is unique per `(user_id, idempotency_key)` and uses a per-user PostgreSQL
  advisory transaction lock;
- permits at most 12 changed files and three classified attempts by contract;
- runs only in an isolated workspace and stops at a Draft PR;
- never enables auto-merge, production deployment, live OAuth, live billing or
  a production database migration.

The frontend never grants the entitlement. It displays only the server response
from `GET /api/user/agent/rescue/entitlement`.

## API

All routes require the existing HTTP-only Sovereign session.

| Method | Route | Effect |
|---|---|---|
| `GET` | `/api/user/agent/rescue/entitlement` | Read server-side entitlement |
| `POST` | `/api/user/agent/rescue/diagnose` | Read GitHub head; no repo mutation |
| `POST` | `/api/user/agent/rescue/repair` | Reserve one idempotent pack and execute |
| `GET` | `/api/user/agent/rescue/repairs/<id>` | Read tenant-owned repair and job |
| `POST` | `/api/user/agent/rescue/repairs/<id>/proof-pack` | Read PR/check evidence |

`POST /repair` requires a UUID `Idempotency-Key`. A replay with the same tenant,
repository, base SHA and family returns the existing repair and charges zero
additional credits. A changed request with the same key fails closed.

## Outcome Contract

Every accepted diagnosis produces `sovereign.outcome-contract.v1` with:

- repository, branch and exact base SHA;
- one supported failure family;
- Repair Pack limits;
- success and stop conditions;
- Draft-PR-only and no-auto-merge policy;
- rollback strategy;
- canonical SHA-256 of the contract.

The repair route reconstructs the diagnosis and contract server-side. It never
trusts a client-provided contract hash.

## ProofPack

`sovereign.proof-pack.v1` contains:

- Rescue repair ID and repository;
- base and Draft PR head SHA;
- changed paths and test summary from the persisted agent job;
- exact-head GitHub check runs;
- rollback plan;
- blockers and a canonical proof SHA-256.

It remains incomplete when any of these are missing, when CI is pending or red,
or when check runs do not refer to the same head SHA. A mock, stale deployment,
UI-only flag or old runtime cannot satisfy it.

## Secrets and tenancy

- GitHub tokens are optional, request-scoped and never persisted by Rescue.
- Token-, password-, authorization- and API-key-shaped values are redacted from
  bounded diagnosis, errors, test summaries and ProofPack output.
- Repair rows are always read through `(repair_id, user_id)`.
- Database rows store identifiers, hashes, state and bounded blockers; they do
  not store repository contents, raw logs, model output or credentials.
- OAuth login remains read-only (`read:user`, `user:email`). Repository write
  access remains separate and explicit.

## Deployment

1. Build the backend image from the exact merged commit.
2. Run `045_sovereign_rescue.sql` through the existing migration runner.
3. Verify the migration transaction and schema constraints in a non-production
   preview first.
4. Deploy the immutable backend image and web bundle through the existing
   protected workflows.
5. Read back image digest, source revision, health, FreeLLM route canaries and
   the Rescue endpoints.
6. Run one sandbox checkout-to-entitlement-to-repair-to-Draft-PR canary.

No production migration, deployment, OAuth switch or payment activation is
authorized merely by merging the repository change.

## Rollback

- Before deployment: close the Draft PR.
- After merge but before deployment: revert the merge commit.
- After deployment: redeploy the previously verified immutable image and web
  artifact.
- Database: the table is additive. Application rollback may leave it in place.
  Destructive table removal is intentionally excluded from the automatic
  rollback path.
- Customer repair: close the generated Draft PR or revert its isolated commit.

## Known limitations

- v1 does not repair application bugs outside the three declared families.
- Private repositories require an explicit ephemeral fine-grained GitHub token
  until a tenant-bound GitHub App installation flow is production-approved.
- Runtime verification against a customer production environment is optional
  and requires a separate revision-bound owner approval.
- ProofPack readiness requires GitHub check runs; a repository without checks
  stays visibly incomplete.

