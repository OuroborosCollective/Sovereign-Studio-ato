# Adversarial Control State Assurance (ACSA) v1

## Overview

This document describes the pure, deterministic contract layer for ACSA. This lane defines the allowed mutation operators, case definitions, and single-variable invariant enforcement. It performs **no** network, database, filesystem, clock, or random access.

## Design Principles

1. **Pure Contract Layer**: Only defines data structures and validation rules
2. **Fail-Closed**: Invalid inputs are rejected with clear error messages
3. **Single-Variable Invariant**: Exactly one security dimension may differ between baseline and mutant
4. **Canonical Hashes**: All hashes are computed deterministically from canonical JSON
5. **Secret Safety**: Secret-shaped raw fields are never stored in contracts or receipts

## Operator Registry (V1)

The following operators are defined as a static allowlist:

| Operator | Allowed Security Dimension | Requires Runtime | Requires Target Readback |
|---------|---------------------------|-----------------|-------------------------|
| `STALE_REVISION` | revision | Yes | Yes |
| `WRONG_IMAGE_DIGEST` | image_digest | Yes | Yes |
| `TOOL_BINDING_SWAP` | tool_binding | Yes | Yes |
| `OWNER_MISMATCH` | owner | Yes | Yes |
| `CREDENTIAL_REPLAY` | credential | Yes | Yes |
| `RECEIPT_REPLAY` | receipt | Yes | Yes |
| `NONPROD_TO_PRODUCTION` | environment | Yes | Yes |
| `DISALLOWED_EGRESS` | egress_policy | Yes | Yes |
| `MISSING_RUNTIME_EVIDENCE` | runtime_evidence | No | Yes |

## Security Dimensions

Each operator is restricted to mutating exactly one security dimension:

- `revision` - Git repository revision
- `image_digest` - OCI image digest (sha256:...)
- `tool_binding` - Tool-to-operation binding
- `owner` - Principal/credential owner
- `credential` - Authentication credential
- `receipt` - Execution receipt
- `environment` - Deployment environment (dev/test/prod)
- `egress_policy` - Network egress rules
- `runtime_evidence` - Runtime evidence availability

## Data Structures

### ControlMutationCase

Immutable case definition for a control mutation test:

```
ControlMutationCase {
    schema_version: str
    mutation_id: str
    operator: ControlMutationOperator
    repository: str
    repository_revision: str (Git SHA-40)
    control_owner: str
    baseline_contract_sha256: str (SHA-256)
    mutated_contract_sha256: str (SHA-256)
    protected_operation_family: str
    operation_input_sha256: str (SHA-256)
    expected_block_code: Optional[str]
    requires_runtime_execution: bool
    requires_target_readback: bool
    case_sha256: str (SHA-256)
}
```

### ControlMutationReceipt

Immutable receipt for a control mutation test result:

```
ControlMutationReceipt {
    schema_version: str
    case_sha256: str (SHA-256)
    repository_revision: str (Git SHA-40)
    runtime_revision: Optional[str] (Git SHA-40)
    image_digest: Optional[str] (sha256:...)
    execution_receipt_sha256: Optional[str] (SHA-256)
    target_readback_sha256: Optional[str] (SHA-256)
    observed_block_code: Optional[str]
    verdict: Literal["MUTANT_KILLED", "MUTANT_SURVIVED", "UNVERIFIED", "CONTRADICTED"]
    receipt_sha256: str (SHA-256)
}
```

## Verdict Rules

| Condition | Verdict |
|----------|---------|
| case_sha256 mismatch | CONTRADICTED |
| repository_revision mismatch | CONTRADICTED |
| requires_target_readback=True but target_readback_sha256 missing | UNVERIFIED |
| requires_runtime_execution=True but execution_receipt_sha256 missing | UNVERIFIED |
| observed_block_code == expected_block_code | MUTANT_KILLED |
| observed_block_code != expected_block_code | MUTANT_SURVIVED |
| No observed block code | UNVERIFIED |

## Validation Rules

### Canonical Formats

- Git SHA: exactly 40 lowercase hex characters
- SHA-256: exactly 64 lowercase hex characters  
- OCI digest: `sha256:<64 hex>`
- Identifiers: `[a-z][a-z0-9_.:/@-]{1,119}`

### Forbidden Values

- Floats, NaN, Infinity
- Implicit time fields (timestamp, created_at, now, etc.)
- Secret-shaped fields (api_key, token, password, credential, etc.)
- Raw prompts, file contents, database rows

### Single-Variable Invariant

- Baseline and mutant must share operation identity
- Exactly one security dimension may differ
- The differing dimension must match the operator's allowed dimension
- Multi-dimensional mutants are blocked

## File Structure

```
backend/agent_runtime/
├── control_mutation_cases.py     # Case definitions and validation
├── control_mutation_receipts.py # Receipt definitions and verdict computation

backend/tests/
├── test_control_mutation_contract.py        # Case contract tests
├── test_control_mutation_receipts.py       # Receipt tests
└── test_control_mutation_single_variable.py # Single-variable invariant tests
```

## Relationship to Other Modules

- **proof_verdict.py**: ACSA extends the pure proof envelope concept
- **mutation_evidence_layer.py**: ACSA provides potential receipt types for the `negative_access_test` requirement in `SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1`
- **environment_mcp_execution.py**: ACSA shares canonical hash patterns and secret-safety rules

## Acceptance Criteria

- [x] Existing proof/mutation/environment enums reused where possible
- [x] Static V1 operator allowlist
- [x] Single-variable invariant technically enforced
- [x] Canonical case/receipt hashes
- [x] Secret-safety (no raw credentials/tokens in contracts)
- [x] No network/DB/filesystem/clock/random in pure contract core
- [x] No new evidence/mutation truth (positive runtime claims are outside this lane)
