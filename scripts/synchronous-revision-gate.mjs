#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';

const SHA40 = /^[0-9a-f]{40}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ALLOWED_ARGUMENTS = new Set(['mode', 'head', 'backend', 'mcp', 'runtime', 'report']);

function fail(message) {
  throw new Error(message);
}

function readJson(path) {
  let value;
  try {
    value = JSON.parse(fs.readFileSync(path, 'utf8'));
  } catch (error) {
    fail(`evidence_json_invalid:${path}:${error instanceof Error ? error.message : 'unknown'}`);
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail(`evidence_json_not_object:${path}`);
  }
  return value;
}

function parseArgs(argv) {
  const values = {};
  for (let index = 2; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    const name = key?.startsWith('--') ? key.slice(2) : '';
    if (!ALLOWED_ARGUMENTS.has(name) || value === undefined || Object.hasOwn(values, name)) {
      fail('usage: --mode ci|release --head <sha> --backend <json> --mcp <json> [--runtime <json>] [--report <json>]');
    }
    values[name] = value;
  }
  return values;
}

function assertImageEvidence(kind, evidence, head) {
  const revision = String(evidence.sourceRevision ?? '');
  const repository = String(evidence.imageRepository ?? '');
  const digest = String(evidence.imageDigest ?? '');
  if (evidence.schemaVersion !== 'sovereign.immutable-image-evidence.v1') {
    fail(`${kind}_schema_invalid`);
  }
  if (revision !== head) {
    fail(`${kind}_revision_contradicted:${revision || 'missing'}`);
  }
  if (!repository.startsWith('ghcr.io/ouroboroscollective/')) {
    fail(`${kind}_repository_invalid`);
  }
  if (!DIGEST.test(digest)) {
    fail(`${kind}_digest_invalid`);
  }
  if (evidence.immutablePublished !== true || evidence.ociRevisionLabelVerified !== true) {
    fail(`${kind}_immutable_or_oci_label_unverified`);
  }
  return { repository, digest, revision };
}

function assertRuntimeEvidence(runtime, head, backend, mcp) {
  if (runtime.schemaVersion !== 'sovereign.coordinated-runtime-readback.v1') {
    fail('runtime_schema_invalid');
  }
  const backendRuntime = runtime.backend && typeof runtime.backend === 'object' ? runtime.backend : {};
  const mcpRuntime = runtime.mcp && typeof runtime.mcp === 'object' ? runtime.mcp : {};
  const broker = runtime.broker && typeof runtime.broker === 'object' ? runtime.broker : {};
  for (const [name, item, expected] of [
    ['backend', backendRuntime, backend],
    ['mcp', mcpRuntime, mcp],
  ]) {
    if (item.sourceRevision !== head || item.imageDigest !== expected.digest || item.imageRepository !== expected.repository) {
      fail(`runtime_${name}_identity_contradicted`);
    }
    if (item.healthy !== true || item.ready !== true || item.readbackVerified !== true) {
      fail(`runtime_${name}_health_or_readback_unverified`);
    }
  }
  if (broker.status !== 'BROKER_READY' || broker.mcpProtocolReady !== true) {
    fail('runtime_broker_or_protocol_unverified');
  }
}

function main() {
  const args = parseArgs(process.argv);
  const mode = args.mode;
  const head = String(args.head ?? '');
  if (!['ci', 'release'].includes(mode) || !SHA40.test(head)) {
    fail('mode_or_head_invalid');
  }
  if (!args.backend || !args.mcp) {
    fail('backend_and_mcp_evidence_required');
  }
  const backend = assertImageEvidence('backend', readJson(args.backend), head);
  const mcp = assertImageEvidence('mcp', readJson(args.mcp), head);
  if (backend.repository === mcp.repository || backend.digest === mcp.digest) {
    fail('component_image_identity_not_distinct');
  }
  if (mode === 'release') {
    if (!args.runtime) {
      fail('runtime_readback_evidence_required_for_release');
    }
    assertRuntimeEvidence(readJson(args.runtime), head, backend, mcp);
  }
  const output = {
    schemaVersion: 'sovereign.synchronous-revision-gate.v1',
    status: mode === 'release' ? 'RELEASE_RUNTIME_VERIFIED' : 'IMAGE_REVISION_SYNCHRONIZED',
    mode,
    sourceRevision: head,
    backend,
    mcp,
    runtimeReadbackRequiredForPromotion: true,
    evidenceSha256: '',
  };
  const canonical = JSON.stringify(output);
  output.evidenceSha256 = crypto.createHash('sha256').update(canonical).digest('hex');
  if (args.report) {
    fs.writeFileSync(args.report, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
  }
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`SYNCHRONOUS_REVISION_GATE_BLOCKED:${error instanceof Error ? error.message : 'unknown'}\n`);
  process.exit(2);
}
