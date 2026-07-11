import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { promisify } from 'node:util';
import path from 'node:path';
import process from 'node:process';

const execFileAsync = promisify(execFile);
const root = process.cwd();
const templatePath = path.resolve(root, process.env.VPS_EVIDENCE_TEMPLATE ?? 'config/vps-evidence-template.json');
const outputPathInput = process.env.VPS_EVIDENCE_OUTPUT ?? 'runtime-evidence/vps-evidence.json';
const resolvedOutputPath = path.resolve(root, outputPathInput);
const outputPathRelative = path.relative(root, resolvedOutputPath);
if (outputPathRelative.startsWith('..') || path.isAbsolute(outputPathRelative)) {
  throw new Error(`VPS_EVIDENCE_OUTPUT must resolve within project root: ${root}`);
}
const outputPath = resolvedOutputPath;
const timeoutMs = Number(process.env.VPS_EVIDENCE_TIMEOUT_MS ?? 10000);
const allowedHttpHosts = new Set(
  String(process.env.VPS_EVIDENCE_ALLOWED_HTTP_HOSTS ?? '')
    .split(',')
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean),
);

function clip(value, max = 800) {
  const text = String(value ?? '').trim();
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function normalizeHttpUrl(value) {
  let parsed;
  try {
    parsed = new URL(String(value ?? '').trim());
  } catch {
    throw new Error('invalid URL');
  }

  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(`unsupported protocol: ${parsed.protocol}`);
  }

  if (!parsed.hostname) {
    throw new Error('missing hostname');
  }

  if (parsed.username || parsed.password) {
    throw new Error('URL credentials are not allowed');
  }

  if (allowedHttpHosts.size > 0 && !allowedHttpHosts.has(parsed.hostname.toLowerCase())) {
    throw new Error(`hostname not allowed: ${parsed.hostname}`);
  }

  return parsed.toString();
}

async function run(command, args = [], options = {}) {
  try {
    const result = await execFileAsync(command, args, {
      cwd: root,
      timeout: timeoutMs,
      maxBuffer: 1024 * 1024,
      env: process.env,
      ...options,
    });
    return { ok: true, exitStatus: 0, stdout: clip(result.stdout), stderr: clip(result.stderr) };
  } catch (error) {
    return {
      ok: false,
      exitStatus: Number.isInteger(error?.code) ? error.code : null,
      stdout: clip(error?.stdout),
      stderr: clip(error?.stderr || error?.message),
    };
  }
}

async function shell(command) {
  return run('/bin/sh', ['-lc', command]);
}

async function gitSha() {
  const result = await run('git', ['rev-parse', 'HEAD']);
  return result.ok ? result.stdout : null;
}

async function httpCheck(url) {
  const started = performance.now();
  let target;
  try {
    target = normalizeHttpUrl(url);
  } catch (error) {
    return {
      status: 'FAIL',
      http_status: null,
      latency_ms: Math.round(performance.now() - started),
      evidence: `GET ${clip(url)} rejected: ${clip(error?.message)}`,
    };
  }

  try {
    const response = await fetch(target, {
      redirect: 'manual',
      signal: AbortSignal.timeout(timeoutMs),
      headers: { accept: 'application/json,text/plain,*/*' },
    });
    const body = clip(await response.text(), 500);
    return {
      status: response.ok ? 'PASS' : 'FAIL',
      http_status: response.status,
      latency_ms: Math.round(performance.now() - started),
      evidence: `GET ${target} -> ${response.status}${body ? `; ${body}` : ''}`,
    };
  } catch (error) {
    return {
      status: 'FAIL',
      http_status: null,
      latency_ms: Math.round(performance.now() - started),
      evidence: `GET ${target} failed: ${clip(error?.message)}`,
    };
  }
}

async function commandCheck(command) {
  const result = await shell(command);
  return {
    status: result.ok ? 'PASS' : 'FAIL',
    exit_status: result.exitStatus,
    evidence: clip([result.stdout, result.stderr].filter(Boolean).join(' | ') || `${command} exited ${result.exitStatus}`),
  };
}

async function dockerEvidence(container) {
  if (!container) return {};
  const format = '{{json .}}';
  const result = await run('docker', ['inspect', '--format', format, container]);
  if (!result.ok) return { container, inspect_error: result.stderr || 'docker inspect failed' };
  try {
    const inspected = JSON.parse(result.stdout);
    return {
      container,
      image: inspected.Config?.Image ?? null,
      image_id: inspected.Image ?? null,
      started_at: inspected.State?.StartedAt ?? null,
      restart_count: inspected.RestartCount ?? null,
    };
  } catch (error) {
    return { container, inspect_error: `invalid docker inspect JSON: ${clip(error?.message)}` };
  }
}

async function hashCriticalFiles() {
  const files = (process.env.VPS_CRITICAL_FILES ?? '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
  const hashes = {};
  for (const file of files) {
    const absolute = path.resolve(root, file);
    try {
      const content = await readFile(absolute);
      hashes[file] = createHash('sha256').update(content).digest('hex');
    } catch (error) {
      hashes[file] = `ERROR:${clip(error?.message, 200)}`;
    }
  }
  return hashes;
}

const httpSources = {
  'backend.local.health': 'VPS_BACKEND_LOCAL_HEALTH_URL',
  'backend.proxy.health': 'VPS_BACKEND_PROXY_HEALTH_URL',
  'toolchain.status': 'VPS_TOOLCHAIN_STATUS_URL',
  'toolchain.read_canary': 'VPS_TOOLCHAIN_READ_CANARY_URL',
  'llm.routing': 'VPS_LLM_ROUTING_URL',
  'llm.model_canary': 'VPS_LLM_MODEL_CANARY_URL',
};

const commandSources = {
  'database.select1': 'VPS_DATABASE_SELECT1_COMMAND',
  'database.migrations': 'VPS_DATABASE_MIGRATIONS_COMMAND',
  'pattern.local': 'VPS_PATTERN_LOCAL_COMMAND',
  'vector.database': 'VPS_VECTOR_DATABASE_COMMAND',
  'agent.routes': 'VPS_AGENT_ROUTES_COMMAND',
  'agent.read_canary': 'VPS_AGENT_READ_CANARY_COMMAND',
  'security.secret_scan': 'VPS_SECRET_SCAN_COMMAND',
};

const template = JSON.parse(await readFile(templatePath, 'utf8'));
const localSha = await gitSha();
const expectedSha = process.env.EXPECTED_SHA || template.expected_sha || localSha;
const reportedSha = process.env.DEPLOYED_SHA || localSha;
const docker = await dockerEvidence(process.env.VPS_CONTAINER);

const checks = [];
for (const check of template.checks) {
  const httpEnv = httpSources[check.id];
  const commandEnv = commandSources[check.id];
  if (httpEnv && process.env[httpEnv]) {
    checks.push({ ...check, ...(await httpCheck(process.env[httpEnv])) });
  } else if (commandEnv && process.env[commandEnv]) {
    checks.push({ ...check, ...(await commandCheck(process.env[commandEnv])) });
  } else {
    checks.push({
      ...check,
      status: 'UNKNOWN',
      evidence: `Not configured: ${httpEnv ?? commandEnv ?? 'no runtime source mapped'}`,
    });
  }
}

const blockers = [];
if (!reportedSha) blockers.push('Unable to resolve deployed Git SHA.');
if (expectedSha && reportedSha && expectedSha !== reportedSha) {
  blockers.push(`Deployed SHA ${reportedSha} does not match expected SHA ${expectedSha}.`);
}
if (docker.inspect_error) blockers.push(docker.inspect_error);
for (const check of checks) {
  if (check.status === 'FAIL') blockers.push(`${check.id}: ${check.evidence}`);
}

const report = {
  ...template,
  expected_sha: expectedSha,
  collected_at: new Date().toISOString(),
  collector: process.env.VPS_EVIDENCE_COLLECTOR || template.collector || 'vps-agent',
  deployed: {
    ...template.deployed,
    reported_sha: reportedSha,
    ...docker,
    critical_file_hashes: await hashCriticalFiles(),
  },
  checks,
  blockers,
  notes: [
    ...(template.notes ?? []),
    'UNKNOWN means no real runtime source was configured; it is never treated as PASS.',
  ],
};

await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(`VPS evidence written to ${outputPath}`);
console.log(`Checks: ${checks.filter((check) => check.status === 'PASS').length} PASS, ${checks.filter((check) => check.status === 'FAIL').length} FAIL, ${checks.filter((check) => check.status === 'UNKNOWN').length} UNKNOWN`);

if (process.env.VPS_EVIDENCE_FAIL_ON_BLOCKER === '1' && blockers.length > 0) {
  process.exitCode = 1;
}
