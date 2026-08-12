const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const workflow = fs.readFileSync(
  path.join(root, '.github/workflows/sovereign-coordinated-release.yml'),
  'utf8',
);

function count(source, fragment) {
  return source.split(fragment).length - 1;
}

test('coordinated release is the single main-head image truth surface', () => {
  assert.match(workflow, /name: Sovereign Coordinated Release Gate/);
  assert.match(workflow, /Checkout exact main revision/);
  assert.match(workflow, /Wait for exact-revision image workflows/);
  assert.match(workflow, /sovereign-backend-image\.yml/);
  assert.match(workflow, /sovereign-chatgpt-mcp\.yml/);
  assert.doesNotMatch(workflow, /synchronous-revision-control\.yml/);
  assert.doesNotMatch(workflow, /actions\/download-artifact@v4/);
});

test('coordinated release waits for the full producer critical path and accepts exact-head refreshes', () => {
  assert.match(workflow, /timeout-minutes: 105/);
  assert.match(workflow, /attempt <= 540/);
  assert.match(workflow, /\['push', 'workflow_dispatch'\]/);
  assert.match(workflow, /String\(run\.head_sha \|\| ''\)\.toLowerCase\(\) === expected/);
  assert.match(workflow, /EXACT_REVISION_IMAGE_WORKFLOWS_TIMEOUT/);
});

test('coordinated release revalidates current main before registry work and before upload', () => {
  assert.equal(count(workflow, "ref: 'heads/main'"), 2);
  assert.match(workflow, /SOURCE_REVISION_IS_NOT_CURRENT_MAIN:/);
  assert.match(workflow, /SOURCE_REVISION_IS_NOT_CURRENT_MAIN_AT_UPLOAD:/);
  assert.match(workflow, /AUTHORITATIVE_REVISION: \$\{\{ steps\.authoritative_main_final\.outputs\.head \}\}/);
});

test('manifest records immutable identities but blocks runtime promotion without independent target-system evidence', () => {
  assert.match(workflow, /schemaVersion': 'sovereign\.coordinated-release-manifest\.v1'/);
  assert.match(workflow, /'deploymentPerformed': False/);
  assert.match(workflow, /'runtimePromotionStatus': 'BLOCKED_PENDING_INDEPENDENT_TARGET_SYSTEM_READBACK'/);
  assert.match(workflow, /'authoritativeMainRevision': authoritative_revision/);
  assert.match(workflow, /hashlib\.sha256\(canonical\)/);
});

test('Docker inspect templates use valid Go-template quotes', () => {
  assert.match(workflow, /--format '\{\{index \.Config\.Labels "org\.opencontainers\.image\.revision"\}\}'/);
  assert.doesNotMatch(workflow, /--format '\{\{index \.Config\.Labels \\"org\.opencontainers\.image\.revision\\"\}\}'/);
});
