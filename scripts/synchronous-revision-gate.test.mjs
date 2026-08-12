import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const root = new URL('.', import.meta.url).pathname;
const gate = join(root, 'synchronous-revision-gate.mjs');
const head = '463dbbf88e44ee24b10624004f818b2283c6794d';
const backendDigest = 'sha256:d477eb7dd2786557a8d5c0aa3b65edbc54e53e35d7a03fd1764a194d6e51fb93';
const mcpDigest = 'sha256:314b3cad9046877dfd5a1ddf79bee129fbc86d60867a9b070ddd5aea280b3658';

function image(repository, digest, revision = head) {
  return {
    schemaVersion: 'sovereign.immutable-image-evidence.v1',
    sourceRevision: revision,
    imageRepository: repository,
    imageDigest: digest,
    immutablePublished: true,
    ociRevisionLabelVerified: true,
  };
}

function run(mode, backend, mcp, runtime) {
  const dir = mkdtempSync(join(tmpdir(), 'sync-revision-gate-'));
  try {
    const backendPath = join(dir, 'backend.json');
    const mcpPath = join(dir, 'mcp.json');
    writeFileSync(backendPath, JSON.stringify(backend));
    writeFileSync(mcpPath, JSON.stringify(mcp));
    const args = [gate, '--mode', mode, '--head', head, '--backend', backendPath, '--mcp', mcpPath];
    if (runtime) {
      const runtimePath = join(dir, 'runtime.json');
      writeFileSync(runtimePath, JSON.stringify(runtime));
      args.push('--runtime', runtimePath);
    }
    return spawnSync('node', args, { encoding: 'utf8' });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const backend = image('ghcr.io/ouroboroscollective/sovereign-backend', backendDigest);
const mcp = image('ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp', mcpDigest);

test('accepts two distinct immutable component images bound to one source head', () => {
  const result = run('ci', backend, mcp);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /IMAGE_REVISION_SYNCHRONIZED/);
});

test('blocks a backend image bound to a different source head', () => {
  const result = run('ci', image(backend.imageRepository, backendDigest, '2b3fcc4eadf4d1fc98a73adf74fcadb73951c6d2'), mcp);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /backend_revision_contradicted/);
});

test('blocks release mode without a coordinated runtime readback', () => {
  const result = run('release', backend, mcp);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /runtime_readback_evidence_required_for_release/);
});

test('accepts release mode only with exact backend, MCP and broker readbacks', () => {
  const runtime = {
    schemaVersion: 'sovereign.coordinated-runtime-readback.v1',
    backend: { sourceRevision: head, imageRepository: backend.imageRepository, imageDigest: backendDigest, healthy: true, ready: true, readbackVerified: true },
    mcp: { sourceRevision: head, imageRepository: mcp.imageRepository, imageDigest: mcpDigest, healthy: true, ready: true, readbackVerified: true },
    broker: { status: 'BROKER_READY', mcpProtocolReady: true },
  };
  const result = run('release', backend, mcp, runtime);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /RELEASE_RUNTIME_VERIFIED/);
});
