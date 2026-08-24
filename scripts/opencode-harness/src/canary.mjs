import { createHash } from 'node:crypto';
import { realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { createOpencode } from '@opencode-ai/sdk';

const RECEIPT_SCHEMA = 'sovereign.opencode-sdk-canary-receipt.v1';
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

async function resolveWorkspace(value) {
  if (!path.isAbsolute(value)) throw new Error('SOVEREIGN_OPENCODE_WORKSPACE must be an absolute path');
  const resolved = await realpath(value);
  const metadata = await stat(resolved);
  if (!metadata.isDirectory()) throw new Error('SOVEREIGN_OPENCODE_WORKSPACE must resolve to a directory');
  return resolved;
}

async function main() {
  const providerModel = assertProviderModel(requiredEnv('SOVEREIGN_OPENROUTER_PROVIDER_MODEL'));
  const keyFile = await resolveRequiredFile(requiredEnv('SOVEREIGN_OPENROUTER_KEY_FILE'), 'SOVEREIGN_OPENROUTER_KEY_FILE');
  const workspace = await resolveWorkspace(requiredEnv('SOVEREIGN_OPENCODE_WORKSPACE'));
  const port = Number(process.env.SOVEREIGN_OPENCODE_PORT || DEFAULT_PORT);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('SOVEREIGN_OPENCODE_PORT must be a user-space TCP port');

  // OpenCode inherits cwd when it starts its local server. The harness may only
  // observe an already isolated Sovereign workspace; it never points at the
  // repository checkout or host root implicitly.
  process.chdir(workspace);

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

    const outputSha256 = sha256(JSON.stringify(structured));
    const receipt = {
      schemaVersion: RECEIPT_SCHEMA,
      harness: 'opencode-sdk',
      transport: 'openrouter',
      providerModel,
      opencodeModel,
      serverHealthy: true,
      structuredOutputVerified: true,
      toolMutationVerified: false,
      inputSha256: sha256(canaryPrompt),
      outputSha256,
      sessionIdSha256: sha256(sessionId),
      opencodeVersion: typeof healthResult.version === 'string' ? healthResult.version : null,
    };
    process.stdout.write(`${JSON.stringify(receipt)}\n`);
  } finally {
    opencode?.server?.close();
  }
}

main().catch((error) => {
  process.stderr.write(`opencode_sdk_canary_failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
