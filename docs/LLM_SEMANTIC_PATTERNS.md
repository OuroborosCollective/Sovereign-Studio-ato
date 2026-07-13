# LLM Semantic Learning Patterns — Sovereign Studio ATO
**Version:** 1.0  
**Generated:** 2026-07-13  
**Purpose:** Reusable semantic schemas and decision patterns for autonomous coding agents  
**Audience:** AI/LLM systems, Copilot agents, no-code automation tools

---

## 1. FOUNDATIONAL AXIOMS (Invariants)

### Axiom 1.0: Runtime Truth First
```
RULE: Build runtime that produces truth.
       Do NOT build UI that invents truth.
       UI may ONLY display verified runtime state.

SEMANTIC SCHEMA:
{
  "pattern": "runtime_truth_first",
  "category": "architectural_principle",
  "enforcement": "mandatory",
  "violations": [
    "UI state without runtime backing",
    "mocked success states",
    "hardcoded percentages",
    "DOM-scraped truth",
    "unverified status claims"
  ],
  "evidence_sources": [
    "sequentialRuntime",
    "repoSnapshotStatus",
    "workflowReport",
    "telemetry"
  ]
}
```

### Axiom 1.1: Causal Chain Integrity
```
SEQUENCE: Input → Intent → Route → Runtime → Result → State → Next Action

SEMANTIC CHECK:
Each step MUST be logically derivable from previous step's OUTPUT.
NOT from: button click, visible text, UI appearance, static assumption.

PATTERN: causal_workflow_validation
{
  "step_n": { "produces": "state_n", "measurable": true },
  "step_n+1": { "depends_on": "state_n", "derivable": true },
  "validity": "state_n must exist in runtime before step_n+1 initiates"
}
```

---

## 2. RUNTIME STATE PATTERNS

### Pattern 2.0: Truth Source Hierarchy
```json
{
  "pattern_id": "truth_source_hierarchy",
  "priority_order": [
    {
      "rank": 1,
      "source": "production_runtime",
      "example": "active workflow execution result",
      "confidence": "highest"
    },
    {
      "rank": 2,
      "source": "storage_state",
      "example": "database row, persisted session",
      "confidence": "high"
    },
    {
      "rank": 3,
      "source": "contract_verified",
      "example": "test suite green, type check pass",
      "confidence": "medium_high"
    },
    {
      "rank": 4,
      "source": "inference_from_logs",
      "example": "deduced from workflow logs",
      "confidence": "medium"
    },
    {
      "rank": 5,
      "source": "ui_state",
      "example": "component state, DOM text",
      "confidence": "never_use_as_truth"
    }
  ],
  "usage_rule": "Always consult higher rank first. Contradict lower ranks when conflict detected."
}
```

### Pattern 2.1: State Transition Classification
```typescript
// SEMANTIC SCHEMA FOR STATE CLASSIFICATION
type StateClassification = 
  | "planned"       // Exists in docs/intentions only
  | "created"       // Object instantiated (runtime or storage)
  | "tested"        // Passed functional/unit tests
  | "merged"        // Committed to branch
  | "deployed"      // Shipped to production environment
  | "verified"      // Health check + dependent runtime confirmed working

// INVALID CLAIMS:
// ❌ "deployed" if not "verified"
// ❌ "verified" if health-check failed
// ❌ "merged" if CI not green
// ❌ "tested" from UI alone (needs test file + execution proof)
```

---

## 3. CODE CHANGE PATTERNS

### Pattern 3.0: Safe File Modification Strategy
```json
{
  "pattern_id": "safe_file_modification",
  "file_size_categories": [
    {
      "size": "< 500 lines",
      "strategy": "full_file_replace_allowed",
      "precondition": "all_tests_green",
      "evidence_required": "test_execution_log"
    },
    {
      "size": "500-2000 lines",
      "strategy": "search_replace_blocks_with_context",
      "precondition": "exact_match_count_verified",
      "max_blocks_per_change": 3,
      "evidence_required": ["match_count_proof", "test_result"]
    },
    {
      "size": "> 2000 lines",
      "strategy": "branch_pr_only_no_direct_main",
      "precondition": "multiple_test_gates_green",
      "must_include": ["draft_pr", "workflow_watch", "review_step"],
      "forbidden": ["direct_main_commit", "force_push"]
    }
  ],
  "conflict_resolution": "Get file SHA via getfile, attempt create, catch 409, retry with SHA"
}
```

### Pattern 3.1: Change Size & Revert-ability Classification
```
SMALL:     < 50 lines, 1 file, < 2 concerns  → Revert-able by single inverse-commit
MEDIUM:    < 200 lines, 2-3 files, clear cause → Revert-able with care, test both paths
LARGE:     > 200 lines OR > 3 files OR cross-layer → Requires feature-branch, full regression test
BREAKING:  Alters schema, API surface, config → MUST draft PR, explicit rollback plan

RULE: Every change ≤ MEDIUM scope or must be in PR with green workflow.
      No direct-to-main commits for LARGE/BREAKING without private runtime contract.
```

---

## 4. ARCHITECTURE BOUNDARY PATTERNS

### Pattern 4.0: Protected Product Shape
```
INVARIANT: Protect these boundaries:

LEFT SIDE:    GitHub tree + user input (idea/order)
CENTER:       Chat interface + matrix editor + live status dashboard
RIGHT SIDE:   History log + plain-language analysis
FREE FIRST:   No keys required for baseline routing
GATES:        Visible fix loop on errors; user confirmation before write

IMPLEMENTATION RULE:
{
  "before_github_write": {
    "validation_gates": [
      { "gate": "package_ready", "runner": "sovereignFunctionalGuards" },
      { "gate": "file_review", "runner": "human_or_automated_scan" },
      { "gate": "diff_context_loaded", "runner": "diffReport_check" },
      { "gate": "draft_pr_only", "runner": "branch_creation_service" }
    ],
    "never_auto_merge": true,
    "never_direct_main": true
  }
}
```

### Pattern 4.1: God Component Detection & Refactor
```json
{
  "pattern_id": "god_component_detection",
  "warning_signs": [
    { "indicator": "useState_count > 20", "severity": "high" },
    { "indicator": "useEffect_count > 10", "severity": "high" },
    { "indicator": "lines_of_code > 3000", "severity": "critical" },
    { "indicator": "subcomponents_in_same_file > 5", "severity": "high" },
    { "indicator": "mixed_concerns", "examples": ["UI + runtime + helpers + business logic"] }
  ],
  "refactor_strategy": {
    "phase_1": "Extract pure helpers to runtime/**",
    "phase_2": "Extract UI subcomponents to separate files",
    "phase_3": "Group state with useReducer",
    "phase_4": "One change per SEARCH/REPLACE, one PR per phase",
    "no_action": "full_file_rewrite_ever"
  },
  "evidence": "Current example: BuilderContainer.tsx ~4682 lines, 3000+ lines before main function"
}
```

---

## 5. TESTING & VERIFICATION PATTERNS

### Pattern 5.0: Test Gate Mapping
```typescript
// SEMANTIC SCHEMA FOR TEST EXECUTION TRUTH
interface TestGateTruth {
  scriptName: string;           // e.g., "test:release-gate"
  files_executed: string[];     // Actual test files that run
  coverage_scope: "unit" | "integration" | "e2e" | "smoke" | "full";
  ci_workflow_runs: boolean;    // Does .github/workflows/** run it?
  manual_only: boolean;
  evidence: {
    package_json_ref: string;   // "npm run X" line
    workflow_file: string;      // Path to workflow that runs it
    last_run_timestamp: string;
    status: "green" | "red" | "unknown"
  };
}

// INVALID CLAIMS:
// ❌ "All tests pass" without mapping each test to a gate
// ❌ "Release gate includes this test" without workflow proof
// ❌ UI console log "tests passed" as evidence
```

### Pattern 5.1: Green Gate Checklist
```
REQUIRED BEFORE ANY CODE SHIP:

□ npm run audit:sovereign        → Reports no-mock violations
□ npm run type-check            → Zero TypeScript errors
□ npm run test:run              → All suites green
□ npm run build                 → Artifact produced
□ npm run test:release-gate     → CI gate passes (if PR)

SPECIAL CASES:
  - Android debug APK: npx cap build android (if mobile changes)
  - Secrets check: grep -r "VITE_" .env* (find exposed keys)
  - Network/Auth: manual test against real GitHub API (no mock)

EVIDENCE ARTIFACT:
  Store: logs/gate-YYYYMMDD-HHMMSS.json
  Include: timestamp, script name, exit code, duration, git SHA
```

---

## 6. SECURITY & SECRET PATTERNS

### Pattern 6.0: Secret Handling Invariant
```json
{
  "pattern_id": "no_secrets_in_artifact_paths",
  "forbidden_paths": [
    "src/**/*.ts",
    "src/**/*.tsx",
    ".github/workflows/**",
    "android/**",
    "tests/**",
    "docs/**",
    "public/**",
    "dist/**",
    ".env (any variant)"
  ],
  "allowed_paths": [
    "environment_variables_only (runtime, memory, process.env)",
    "server-side_owner_flows_only",
    "cloudflare_workers_private_env (CF_AI_TOKEN, PROXY_API_KEY)"
  ],
  "validation_rule": {
    "before_commit": "grep -r '(TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL|BEARER)' src/ → must be zero matches",
    "before_github_write": "Scan generated files for common secret patterns"
  },
  "evidence_source": "audit:sovereign gate must flag any leak"
}
```

### Pattern 6.1: Worker Auth Hardening
```
CLOUDFLARE WORKER SECURITY PATTERN:

CURRENT RISK: If PROXY_API_KEY missing → worker allows unauthenticated requests
REQUIRED FIX: Hard fail if secret not configured

IMPLEMENTATION:
{
  "auth_check": {
    "must_execute": "before_route_matching",
    "if_PROXY_API_KEY_missing": "return_503_or_401",
    "never_return": "200_without_secret",
    "health_endpoint": {
      "allowed": "report configured: false",
      "forbidden": "leak secret status"
    }
  },
  "tests": [
    { "case": "secret_missing", "expect": "503_blocked" },
    { "case": "secret_set_no_header", "expect": "401" },
    { "case": "secret_set_correct_header", "expect": "allow" }
  ]
}
```

---

## 7. MEMORY/REMOTE SYNC NAMING SCHEMA

### Pattern 7.0: Clarified Memory Namespaces
```
CANONICAL DEFINITIONS (use these ONLY):

1. SOLUTION_PATTERN
   - What: Reusable code solution for recurring problems
   - Persistence: Database (solutionPatternPersistence)
   - Runtime handler: solutionPatternMemory
   - Container binding: patternMemoryContainerRuntime
   - Reuse: patternReusePlanner

2. LEARNED_PATTERN
   - What: Runtime learnings from past executions
   - Storage: sovereignLearningMemory
   - Tracking: sovereignSessionMemory
   - Container use: patternMemoryProposalRuntime

3. REMOTE_MEMORY_GATEWAY (canonical name for external sync)
   - What: Bidirectional sync with external memory/KB services
   - Gateway: remoteMemoryGatewayBridge
   - Preview: externalMemorySyncPreview
   - Monitoring: externalMemoryMonitoring
   - Intake: remoteMemoryUpdateIntake
   - Production: remoteMemoryProductionReadiness

NAMING RULE:
  ✓ remoteMemory* for external sync
  ✓ solutionPattern* for reusable solutions
  ✓ sovereignLearning* for runtime learning
  ✗ external* and remote* mixed in same file
  ✗ memory pattern * (too vague)
```

### Pattern 7.1: Memory Module Extraction
```json
{
  "pattern_id": "memory_module_boundary",
  "interdependencies": {
    "remoteMemoryGatewayBridge": [
      "imports: externalMemorySync",
      "imports: sovereignSessionMemory",
      "usage: container runtime"
    ],
    "patternMemoryContainerRuntime": [
      "imports: solutionPatternMemory",
      "imports: solutionPatternPersistence",
      "usage: UI state machine"
    ]
  },
  "extraction_rule": "Do NOT merge without: (a) full import map, (b) test file per module, (c) no circular deps"
}
```

---

## 8. GITHUB WRITE PATH PATTERNS

### Pattern 8.0: Draft PR Publishing Flow
```
CURRENT IMPLEMENTATION:
  Input: package (files[], branch metadata)
  ↓
  Runtime: assertGeneratedPackageReady() [functional guards]
  ↓
  GitHub: Create branch + commit + PR (draft mode)
  ↓
  Watch: workflowReport monitors CI
  ↓
  UI: Display status (verified from runtime, not DOM)

MISSING (HIGH PRIORITY):
  /git/patch endpoint for SEARCH/REPLACE instead of full-file-write

REQUIRED FOR /git/patch:
{
  "auth": "server_secret_required",
  "dryRun": { "type": "boolean", "required": true },
  "expectedSha": { "type": "string", "required": true },
  "search": { "type": "string", "minLength": 5, "maxLength": 5000 },
  "replace": { "type": "string", "maxLength": 10000 },
  "validation": {
    "match_count": "exactly 1 (block 0 matches, block >1 matches)",
    "no_secrets": "grep applied to search/replace",
    "file_size": "max 100KB result",
    "branch_check": "allowed_branches only"
  }
}
```

### Pattern 8.1: Full Auto Guardrails
```
AUTONOMOUS MODE RULES:

Still required (even in Full Auto):
  □ Repo snapshot check (non-empty, has files)
  □ Functional guards pass (no unsafe paths, no dupes)
  □ Generated-file review (list, content scan)
  □ Workflow watch active (reports status)
  □ Branch creation (never direct main)

Never auto (even in Full Auto):
  ✗ Auto-merge to main
  ✗ Direct main commit
  ✗ Skip workflow
  ✗ Bypass guards
  ✗ Process identical snapshots twice

Output: Draft PR only, user must click "Ready for Review" to move to code-review state.
```

---

## 9. WORKFLOW & CI PATTERNS

### Pattern 9.0: Workflow Watch Status Classification
```typescript
interface WorkflowTruth {
  status: "pending" | "in_progress" | "success" | "failure" | "cancelled";
  run_id: string;
  commit_sha: string;
  checks: {
    build: "green" | "red" | "unknown";
    test: "green" | "red" | "unknown";
    lint: "green" | "red" | "unknown";
  };
  evidence: {
    api_response_timestamp: string;
    health_endpoint_ping: boolean;
    error_logs_available: boolean;
  };
  next_action: "blocked" | "wait" | "proceed" | "repair";
}

// INVALID CLAIMS:
// ❌ "Workflow passed" without checking all checks
// ❌ "Merged" status if CI still running
// ❌ Assuming green from UI until workflowReport confirms
```

### Pattern 9.1: Error Classification for Repair Flow
```
FAILURE FAMILY STRUCTURE:

Blocker detected → classify by family → route to repair flow

FAMILIES:
  1. SYNTAX_ERROR (TypeScript, JSX parse fail)
     → Symptom: build fails
     → Evidence: compiler output
     → Repair: quote fix, test locally, push new commit

  2. TEST_FAILURE (unit, integration, e2e)
     → Symptom: specific test assertion fails
     → Evidence: test runner output
     → Repair: logic fix, re-run, merge PR

  3. RUNTIME_MISMATCH (contract violation)
     → Symptom: state doesn't match expected
     → Evidence: telemetry, logs
     → Repair: re-verify truth source, update state machine

  4. SECURITY_FLAG (secret in artifact)
     → Symptom: audit:sovereign detects leak
     → Evidence: audit log + file path
     → Repair: remove secret, re-run audit, force-push new commit

  5. DEPENDENCY_MISSING (import fails)
     → Symptom: module not found
     → Evidence: build or test output
     → Repair: npm install / update version, commit lock file

Repair flow NEVER:
  ✗ Blind retry (loops infinitely)
  ✗ Skip the failing gate
  ✗ Assume user fixed it silently
```

---

## 10. ANDROID-FIRST UI PATTERNS

### Pattern 10.0: Touch & Accessibility Semantics
```json
{
  "pattern_id": "android_first_ui",
  "constraints": {
    "min_touch_target": { "value": 48, "unit": "dp", "wcag": "2.5" },
    "screen_density_handling": "use density-independent pixels",
    "orientation": ["portrait_primary", "landscape_optional"],
    "keyboard_navigation": "all controls reachable without mouse"
  },
  "device_categories": [
    { "name": "phone", "min_width": "360dp", "density": "1x-3x" },
    { "name": "tablet", "min_width": "600dp", "density": "1.5x-2x" }
  ],
  "gesture_patterns": [
    { "action": "tap", "target_size": "48dp", "single_use": true },
    { "action": "long_press", "threshold_ms": 500, "always_haptic": true },
    { "action": "swipe", "horizontal": true, "direction": "left|right" },
    { "action": "drag", "constraint": "must_be_droppable_zone" }
  ]
}
```

---

## 11. DESIGN DECISION PATTERNS

### Pattern 11.0: Matrix-Style Editor Semantics
```
INTERFACE CONTRACT:

LEFT (stable):
  - File tree (GitHub snapshot)
  - Order/idea input

CENTER (mutable):
  - Chat conversation
  - File editor (Monaco, SEARCH/REPLACE enabled)
  - Live status (runtime-backed, not UI-state)

RIGHT (log):
  - History (chronological)
  - Analysis (plain-language interpretation)

RULE: Never add a 4th column or overlay that creates visual confusion.
      Chat is always default surface; fullscreen editor is secondary.
```

### Pattern 11.1: Status Dashboard Truth
```
DISPLAY RULES:

❌ Fake percentages (e.g., "45% complete") without measurable tasks
❌ Animated progress that doesn't correlate to runtime
❌ Status that contradicts deployed workflow state

✓ "Building → running tests → deployed" with actual state enum
✓ "(3/5 guards passed; workflow running; check logs)" with specific facts
✓ "Blocked by: failed type-check" with evidence link

MAPPING:
  runtime_state.status → UI status text
  NOT: UI animation → assumed runtime status
```

---

## 12. MIGRATION & DATA PATTERNS

### Pattern 12.0: Safe Schema Migration
```
MIGRATION RULE:

ALWAYS:
  1. Run in preview/transaction first
  2. Verify row count before/after
  3. Check for schema drift (new columns, renamed fields)
  4. Rollback capability ready (old schema snapshot stored)
  5. Dependent runtime validated (queries still work)

NEVER:
  ✗ Destructive delete without backup
  ✗ Assume "migration succeeded" from log text alone
  ✗ Rename column without alias in queries first
  ✗ Run broad transformation without sampling test

EVIDENCE:
  Store: migrations/YYYYMMDD-HHmmss-{name}.sql
  Include: before snapshot, after snapshot, row-count delta, rollback script
```

---

## 13. PRODUCT CONTRACTS (Key Documentation)

### Pattern 13.0: Required Docs Structure
```
EVERY PROJECT MUST HAVE:

1. AGENTS.md
   - Agent rules (master reference)
   - Unchanging during session

2. SOVEREIGN_READER.md
   - Tool map, module list, best practices
   - Updated per release

3. SOVEREIGN_RUNTIME.md
   - Runtime truth path
   - Provider guardrails
   - Workflow gates

4. SOVEREIGN_GUARDRAILS.md
   - Functional guard implementation
   - Guard list (what blocks, what allows)

5. sovereign.guard.json
   - Config: green gate scripts
   - Forbidden paths
   - Security rules

6. repo.md (auto-generated or hand-maintained)
   - Project description
   - Directory structure
   - Tech stack with verification

VALIDATION:
  - Each file must have: Purpose + Update Schedule
  - No docs-only claims (verify with code)
  - Every architectural rule must appear in both code AND docs
```

---

## 14. DECISION FRAMEWORKS

### Pattern 14.0: Refactor vs. Patch Decision Tree
```
QUESTION: Should I refactor or patch?

1. Is the existing code live and working?
   → YES: Patch (add feature without breaking)
   → NO: Refactor only if all tests mock/stub

2. Is the change < 50 lines and < 2 concerns?
   → YES: Patch (SEARCH/REPLACE)
   → NO: Consider branch + PR

3. Will the patch break existing tests?
   → YES: Must refactor tests first OR use branch
   → NO: Patch is safe

4. Is there a cleaner architectural path?
   → YES + safe + time available: Small refactor + test
   → NO or risky: Patch, defer refactor to next cycle

5. Will refactor take < 1 hour with tests green?
   → YES: Do it
   → NO: Patch + file debt issue for next sprint

OUTPUT:
  - Patch Path: Specific SEARCH/REPLACE + green-gate check
  - Refactor Path: Branch + tests + PR + review + merge
```

### Pattern 14.1: Feature Completeness Checklist
```
A feature is ready for merge ONLY if:

CODE:
  □ New file or change follows repo naming conventions
  □ TypeScript: zero errors (npm run type-check)
  □ ESLint: zero violations (npm run lint)
  □ No hardcoded secrets or mock data in live paths

TESTS:
  □ Unit test written (src/**/*.test.ts)
  □ Test covers success + failure + edge case
  □ Test runs green locally AND in CI
  □ Coverage: new code ≥ 80% (measure with tool)

DOCS:
  □ README/module updated if interface changed
  □ Inline comments explain WHY (not what)
  □ No promises ("will do later")

INTEGRATION:
  □ Runs with npm run build
  □ npm run test:run ← all green
  □ npm run audit:sovereign ← no violations
  □ npm run type-check ← zero errors

RUNTIME:
  □ Feature verified on real runtime (not UI simulation)
  □ Workflow passes (CI green)
  □ Telemetry/logs show expected behavior
  □ No new errors in error classification

EVIDENCE:
  □ Link to passing CI run
  □ Link to test file
  □ Link to PR or commit

BLOCKER: Missing ANY checkbox → do not merge
```

---

## 15. REUSABLE PROMPTS FOR AGENTS

### Pattern 15.0: Structured Agent Request Template
```
AGENT REQUEST (for Copilot, OpenHands, etc.):

CONTEXT:
  Project: [Sovereign Studio ATO / other]
  File: [path/to/file.ts or "entire repo"]
  Scope: [< 50 lines / medium / large]

INTENT:
  [One sentence: what do you want to achieve?]

CONSTRAINTS:
  - Must follow: [relevant axiom/pattern from this doc]
  - Cannot use: [mocks, full-file-replace, direct-to-main]
  - Must include: [tests, types, docs]

REQUEST:
  [Specific action: refactor, add feature, fix bug, extract pattern]

VERIFICATION:
  - This change is small/medium/large (check decision tree)
  - Green gates required: [list specific npm run commands]
  - Evidence file location: [where to store results]

ABORT IF:
  - Change would require rewriting > 200 lines
  - Existing tests would break without being fixed
  - No clear evidence source for runtime truth
```

### Pattern 15.1: Code Review Prompt Template
```
CODE REVIEW REQUEST:

FILE: [path]
CHANGE TYPE: [refactor/feature/fix/security]
SIZE: [small/medium/large]

REVIEW AGAINST:
  □ Pattern 3.0 (safe file modification)
  □ Pattern 4.0 (protected product shape)
  □ Pattern 5.1 (green gate checklist)
  □ Pattern 14.1 (feature completeness)

SPECIFIC QUESTIONS:
  1. Does this change preserve runtime truth invariant?
  2. Are there new dependencies? (check package.json)
  3. Are tests written for new logic?
  4. Does it respect architectural boundaries?
  5. Is there any secret or mock data?

DECISION:
  ✓ APPROVE (merge to branch/PR)
  ⏸ HOLD (needs fixes: ...)
  ✗ REJECT (breaks invariant: ...)
```

---

## 16. SEMANTIC QUERY PATTERNS

### Pattern 16.0: Intent-to-Action Mapping
```json
{
  "semantic_queries": [
    {
      "intent": "I want to add a new feature to BuilderContainer",
      "action": "Extract helper to runtime/**, do NOT modify main container directly",
      "evidence": "Pattern 4.1 (god component)"
    },
    {
      "intent": "The tests are failing",
      "action": "Classify error family (Pattern 9.1), route to repair flow",
      "evidence": "Error in CI log or local npm run test:run"
    },
    {
      "intent": "I'm not sure if this state is real",
      "action": "Consult truth source hierarchy (Pattern 2.0); confirm with runtime",
      "evidence": "sequentialRuntime, workflowReport, telemetry"
    },
    {
      "intent": "Should I use a global variable here?",
      "action": "NO. Use state machine or context. Pattern 6.0 forbids globals in render.",
      "evidence": "audit:sovereign flags global mutation"
    },
    {
      "intent": "How do I patch a large file safely?",
      "action": "Use SEARCH/REPLACE, not full-file-write. Pattern 3.0, Pattern 8.0",
      "evidence": "Expected SHA verification before apply"
    }
  ]
}
```

---

## 17. ANTI-PATTERNS (Explicitly Forbidden)

### Pattern 17.0: Anti-Pattern Catalog
```
DO NOT:

1. ❌ Build UI that claims truth it can't verify
   - Example: progress bar without measurable tasks
   - Fix: Show runtime state enums only

2. ❌ Use mocks, stubs, facades in live paths
   - Example: fake GitHub API response in production
   - Fix: Integration tests only in test/** directories

3. ❌ Create god components (> 3000 lines, > 20 useState)
   - Example: entire app in one BuilderContainer
   - Fix: Extract helpers, subcomponents, state managers

4. ❌ Store secrets in code, repos, logs
   - Example: VITE_API_KEY in src/config.ts
   - Fix: environment_variables + Cloudflare Workers

5. ❌ Auto-merge to main or bypass review
   - Example: "Full Auto" that skips guards
   - Fix: Draft PR always; manual "Ready for Review"

6. ❌ Claim "tests pass" without mapping gates
   - Example: Green console log, but workflow didn't run
   - Fix: Link to CI run, test file, specific test name

7. ❌ Patch large files without exact match count
   - Example: SEARCH/REPLACE matches 2+ times → ambiguous
   - Fix: Block, ask for narrower search term

8. ❌ Ignore schema drift or run migrations blind
   - Example: Rename table column without checking queries
   - Fix: Preview + rollback + validate dependent code

9. ❌ Redirect blame to tools ("the compiler did it")
   - Example: "TypeScript error, just ignore it"
   - Fix: Fix root cause, verify with type-check

10. ❌ Copy docs without verifying code
    - Example: "This module does X" but code does Y
    - Fix: Audit + update docs + add tests
```

---

## 18. IMPLEMENTATION CHECKLIST FOR NEW AGENTS

### Pattern 18.0: Agent Onboarding Checklist
```
New Copilot / Agent starting work on Sovereign Studio:

BEFORE ANY CODE CHANGE:

□ Read this file (LLM_SEMANTIC_PATTERNS.md)
□ Read .openhands/microagents/repo.md (architecture guide)
□ Read AGENTS.md (immutable rules)
□ Understand: Axiom 1.0 (runtime truth first)
□ Confirm: You will NOT build UI that invents state

BEFORE ANY COMMIT:

□ Classify change by size (Pattern 3.1)
□ Verify: Does change respect boundaries? (Pattern 4.0)
□ Check: Are tests required? (Pattern 5.1 checklist)
□ Scan: Any secrets, mocks, hardcoded values? (Pattern 6.0)
□ Run: npm run audit:sovereign, type-check, test:run
□ Evidence: Store gate-run logs in /logs/

BEFORE PR/MERGE:

□ Did you follow refactor vs. patch decision tree? (Pattern 14.0)
□ All feature-completeness checks pass? (Pattern 14.1)
□ CI green + workflow verified? (Pattern 9.0)
□ Code review against template? (Pattern 15.1)
□ Is this a Draft PR (if > SMALL change)?

IF BLOCKER:

□ Classify error family (Pattern 9.1)
□ Document repair path (no blind retry)
□ Evidence: Error logs + affected file + proposed fix
```

---

## 19. SEMANTIC QUERY RESOLUTION LOGIC

### Pattern 19.0: Ambiguous Query Handler
```json
{
  "pattern_id": "ambiguous_query_handler",
  "rule": "If agent/user query is ambiguous, STOP and ask for clarification.",
  "examples": [
    {
      "query": "Fix the error.",
      "ambiguous_parts": ["which error", "which file"],
      "required_clarification": [
        "Is this a runtime error, test failure, or type error?",
        "Which file/line?",
        "What does the error message say?",
        "Evidence: error log or screenshot?"
      ],
      "dont_guess": true
    },
    {
      "query": "Update the memory pattern.",
      "ambiguous_parts": ["which memory namespace", "what change"],
      "required_clarification": [
        "Are you updating solutionPattern, remoteMemory, or sovereignLearning?",
        "What specific change (add field, rename, refactor)?",
        "Will this break existing queries? Have you checked imports?"
      ]
    },
    {
      "query": "Speed up the build.",
      "ambiguous_parts": ["which build", "current bottleneck unknown"],
      "required_clarification": [
        "Is it npm run build, Android APK build, or Docker image?",
        "What's the current timing? (profile first)",
        "Which gate is failing? (type-check, test, lint?)"
      ]
    }
  ]
}
```

---

## 20. INTEGRATION POINTS (for No-Code Tools)

### Pattern 20.0: n8n / BuildShip / Appy Pie Connectors
```
RECOMMENDED AUTOMATION CHAINS:

1. USER INTENT → AGENT PLANNING
   Trigger: Chat message in Sovereign UI
   → Call Perplexity API (or Copilot) with context
   → Parse intent (add feature, fix bug, refactor)
   → Classify scope (small/medium/large)
   → Call appropriate pattern

2. CODE CHANGE → GREEN GATE
   Trigger: File modified in src/
   → npm run audit:sovereign
   → npm run type-check
   → npm run test:run
   → Store logs in /logs/YYYYMMDD-*.json
   → If red: send error to chat (Pattern 9.1 classification)
   → If green: proceed to PR creation

3. PR READY → GITHUB WRITE
   Trigger: User clicks "Publish as Draft PR"
   → Create branch (if not exists)
   → Call /git/patch or full-file-write (based on size)
   → Commit + PR draft mode
   → Start workflow watch (Pattern 9.0)

NODEJS API SKELETON:
   POST /api/change-intent
   POST /api/run-gate
   POST /api/create-draft-pr
   GET /api/workflow-status/{run_id}
   POST /api/classify-error
```

---

## SUMMARY TABLE: Quick Reference

| Pattern ID | Title | Enforced By | Evidence |
|---|---|---|---|
| 1.0 | Runtime Truth First | Code review | test:run + audit |
| 2.0 | Truth Source Hierarchy | Runtime checks | sequentialRuntime |
| 3.0 | Safe File Modification | Agent + review | grep match count |
| 4.0 | Protected Product Shape | UI boundaries | reusable components |
| 5.0 | Test Gate Mapping | npm run gates | .github/workflows |
| 6.0 | No Secrets | audit:sovereign | grep for patterns |
| 7.0 | Memory Naming | Refactoring | import analysis |
| 8.0 | Draft PR Flow | GitHub API | branch + PR creation |
| 9.0 | Workflow Watch | CI integration | GitHub REST API |
| 10.0 | Android-First UI | component tests | touch target >= 48dp |
| 13.0 | Doc Requirements | repo structure | AGENTS.md + runtime.md |
| 14.0 | Refactor vs. Patch | decision tree | file size + risk |
| 17.0 | Anti-Patterns | rejection rules | audit scan |

---

## Usage Instructions for LLMs

### How to Use This File

1. **For Architecture Questions**: Consult Patterns 1-4, 13.
2. **For Code Review**: Patterns 3, 5, 14, 17.
3. **For Testing**: Patterns 5, 9, 18.
4. **For Security**: Patterns 6, 8.
5. **For Refactoring**: Patterns 4, 7, 14.
6. **For Error Diagnosis**: Pattern 9.1 (error families).
7. **For Integration**: Pattern 20.

### Machine-Readable Format

Each pattern is structured as:
```
pattern_id: UNIQUE_IDENTIFIER
category: architectural_principle | testing | security | etc.
enforcement: mandatory | recommended | optional
violations: [list of anti-patterns]
evidence_sources: [where to verify]
```

This format is designed for semantic search and LLM embedding.

---

**Last Updated:** 2026-07-13  
**Maintainer:** GitHub Copilot (OuroborosCollective/Sovereign-Studio-ato)  
**License:** Internal; Reference only  
**Versioning:** Semantic (MAJOR.MINOR.PATCH)
