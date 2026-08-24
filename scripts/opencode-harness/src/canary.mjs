import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, readdir, realpath, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createOpencode } from '@opencode-ai/sdk';

const RECEIPT_SCHEMA = 'sovereign.opencode-sdk-canary-receipt.v2';
const DEFAULT_PORT = 4097;

function requiredEnv(name) {
  const value = String(process.env[name] || '').trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function unwrapSdkData(value) {
  if (value && typeof value === 'object' && 'data' in value && value.data !== undefined) return value.data;
  return value;
}

function assertProviderModel(value) {
  if (!/^[a-z0-9][a-z0-9._-]*\/[a-zA-Z0-9][a-zA-Z0-9._:/-]*$/.test(value)) {
    throw new Error('SOVEREIGN_OPENROUTER_PROVIDER_MODEL must be an exact provider/model id');
  }
  return value;
}

async function resolveRequiredFile(value, label) {
  if (!path.isAbsolute(value)) throw new Error(`${label} must be an absolute path`);
  const resolved = await realpath(value);
  const metadata = await stat(resolved);
  if (!metadata.isFile()) throw new Error(`${label} must resolve to a regular file`);
  return resolved;
}

async function createCanarySandbox() {
  const root = await mkdtemp(path.join(tmpdir(), 'sovereign-opencode-canary-'));
  const project = path.join(root, 'project');
  const config = path.join(root, 'config');
  const data = path.join(root, 'data');
  const cache = path.join(root, 'cache');
  await Promise.all([project, config, data, cache].map((directory) => mkdir(directory, { recursive: true })));
  return { root, project, config, data, cache };
}

function captureEnv(names) {
  return Object.fromEntries(names.map((name) => [name, process.env[name]]));
}

function restoreEnv(snapshot) {
  for (const [name, value] of Object.entries(snapshot)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
}

async function main() {
  const providerModel = assertProviderModel(requiredEnv('SOVEREIGN_OPENROUTER_PROVIDER_MODEL'));
  const keyFile = await resolveRequiredFile(requiredEnv('SOVEREIGN_OPENROUTER_KEY_FILE'), 'SOVEREIGN_OPENROUTER_KEY_FILE');
  const port = Number(process.env.SOVEREIGN_OPENCODE_PORT || DEFAULT_PORT);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('SOVEREIGN_OPENCODE_PORT must be a user-space TCP port');

  // The structured SDK/model canary must not have access to the Sovereign
  // checkout at all. A later, separately approved tool-mutation canary owns the
  // isolated coding workspace. This canary runs from a fresh empty temp project
  // with isolated OpenCode config/data/cache homes and deny-all tool policy.
  const sandbox = await createCanarySandbox();
  const previousCwd = process.cwd();
  const isolatedEnvNames = [
    'HOME',
    'XDG_CONFIG_HOME',
    'XDG_DATA_HOME',
    'XDG_CACHE_HOME',
    'OPENCODE_CONFIG',
    'OPENCODE_CONFIG_DIR',
    'OPENCODE_DISABLE_PROJECT_CONFIG',
    'OPENCODE_PERMISSION',
  ];
  const previousEnv = captureEnv(isolatedEnvNames);
  process.env.HOME = sandbox.root;
  process.env.XDG_CONFIG_HOME = sandbox.config;
  process.env.XDG_DATA_HOME = sandbox.data;
  process.env.XDG_CACHE_HOME = sandbox.cache;
  delete process.env.OPENCODE_CONFIG;
  process.env.OPENCODE_CONFIG_DIR = sandbox.config;
  process.env.OPENCODE_DISABLE_PROJECT_CONFIG = 'true';
  process.env.OPENCODE_PERMISSION = JSON.stringify({ '*': 'deny' });
  process.chdir(sandbox.project);

  const opencodeModel = `openrouter/${providerModel}`;
  const canaryPrompt = 'Return a structured canary receipt with status="ok" and harness="opencode-sdk". Do not modify files, run shell commands, or perform external actions.';
  let opencode;

  try {
    opencode = await createOpencode({
      hostname: '127.0.0.1',
      port,
      timeout: 10_000,
      config: {
        model: opencodeModel,
        autoupdate: false,
        share: 'disabled',
        permission: { '*': 'deny' },
        provider: {
          openrouter: {
            models: {
              [providerModel]: {},
            },
            options: {
              // OpenCode resolves the file itself. The key never enters this
              // process as a string and is never emitted in receipts/logs.
              apiKey: `{file:${keyFile}}`,
            },
          },
        },
      },
    });

    const healthResult = unwrapSdkData(await opencode.client.global.health());
    if (!healthResult || healthResult.healthy !== true) throw new Error('OpenCode SDK server health canary failed');

    const sessionResult = unwrapSdkData(await opencode.client.session.create({
      body: { title: 'Sovereign OpenCode SDK structured canary' },
    }));
    const sessionId = sessionResult && typeof sessionResult.id === 'string' ? sessionResult.id : '';
    if (!sessionId) throw new Error('OpenCode SDK did not return a session id');

    const promptResult = unwrapSdkData(await opencode.client.session.prompt({
      path: { id: sessionId },
      body: {
        model: { providerID: 'openrouter', modelID: providerModel },
        parts: [{ type: 'text', text: canaryPrompt }],
        format: {
          type: 'json_schema',
          retryCount: 1,
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              status: { type: 'string', enum: ['ok'] },
              harness: { type: 'string', enum: ['opencode-sdk'] },
            },
            required: ['status', 'harness'],
          },
        },
      },
    }));

    const info = promptResult && typeof promptResult === 'object' ? promptResult.info : undefined;
    if (info?.error) throw new Error(`OpenCode structured canary returned an error: ${String(info.error?.name || 'unknown')}`);
    const structured = info?.structured_output;
    if (!structured || structured.status !== 'ok' || structured.harness !== 'opencode-sdk') {
      throw new Error('OpenCode structured canary did not return the required schema-bound receipt');
    }

    const sandboxProjectEntries = await readdir(sandbox.project);
    if (sandboxProjectEntries.length !== 0) {
      throw new Error('OpenCode structured canary mutated the empty sandbox project');
    }

    const outputSha256 = sha256(JSON.stringify(structured));
    const receipt = {
      schemaVersion: RECEIPT_SCHEMA,
      harness: 'opencode-sdk',
      transport: 'openrouter',
      providerModel,
      opencodeModel,
      serverHealthy: true,
      structuredOutputVerified: true,
      ephemeralSandboxVerified: true,
      sandboxProjectRemainedEmpty: true,
      projectConfigDisabledConfigured: true,
      toolPermissionsConfiguredDenyAll: true,
      toolMutationVerified: false,
      inputSha256: sha256(canaryPrompt),
      outputSha256,
      sessionIdSha256: sha256(sessionId),
      opencodeVersion: typeof healthResult.version === 'string' ? healthResult.version : null,
    };
    process.stdout.write(`${JSON.stringify(receipt)}\n`);
  } finally {
    opencode?.server?.close();
    process.chdir(previousCwd);
    restoreEnv(previousEnv);
    await rm(sandbox.root, { recursive: true, force: true });
  }
}

main().catch((error) => {
  process.stderr.write(`opencode_sdk_canary_failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
