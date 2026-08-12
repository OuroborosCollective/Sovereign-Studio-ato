const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');

const backendWorkflow = read('.github/workflows/sovereign-backend-image.yml');
const mcpWorkflow = read('.github/workflows/sovereign-chatgpt-mcp.yml');
const syncWorkflow = read('.github/workflows/synchronous-revision-control.yml');
const releaseWorkflow = read('.github/workflows/release-verification.yml');

test('backend and MCP image workflows publish revision-bound immutable evidence', () => {
  for (const [name, source, artifact] of [
    ['backend', backendWorkflow, 'sovereign-backend-immutable-image-evidence-${{ env.SOVEREIGN_REVISION }}'],
    ['mcp', mcpWorkflow, 'sovereign-mcp-immutable-image-evidence-${{ github.sha }}'],
  ]) {
    assert.match(source, /schemaVersion: 'sovereign\.immutable-image-evidence\.v1'/, `${name} evidence schema missing`);
    assert.match(source, /sourceRevision: revision/, `${name} source revision binding missing`);
    assert.match(source, /ociRevisionLabelVerified: true/, `${name} OCI revision verification missing`);
    assert.match(source, new RegExp(artifact.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), `${name} evidence artifact missing`);
  }
});

test('synchronous gate waits for exact-head backend and MCP images and rejects absent runtime evidence in release mode', () => {
  assert.match(syncWorkflow, /workflow_run:/);
  assert.match(syncWorkflow, /Sovereign Backend Immutable Image/);
  assert.match(syncWorkflow, /Sovereign ChatGPT MCP/);
  assert.match(syncWorkflow, /String\(run\.head_sha \|\| ''\)\.toLowerCase\(\) === head/);
  assert.match(syncWorkflow, /EXACT_HEAD_IMAGE_WORKFLOWS_DID_NOT_BECOME_SUCCESSFUL/);
  assert.match(syncWorkflow, /SOURCE_REVISION_IS_NOT_CURRENT_MAIN/);
  assert.match(syncWorkflow, /ref: 'heads\/main'/);
  assert.match(syncWorkflow, /synchronous-revision-gate\.mjs/);
  assert.match(syncWorkflow, /runtime_readback_evidence_path/);
  assert.match(syncWorkflow, /Runtime evidence path is required for release mode/);
  assert.match(syncWorkflow, /actions\/download-artifact@v4/);
});

test('release verification executes synchronous revision contract tests when gate-relevant files change', () => {
  assert.match(releaseWorkflow, /scripts\/synchronous-revision-gate\.mjs/);
  assert.match(releaseWorkflow, /scripts\/synchronous-revision-gate\.contract\.mjs/);
  assert.match(releaseWorkflow, /scripts\/synchronous-revision-workflow\.contract\.cjs/);
  assert.match(releaseWorkflow, /Synchronous Revision Gate Contracts/);
});
