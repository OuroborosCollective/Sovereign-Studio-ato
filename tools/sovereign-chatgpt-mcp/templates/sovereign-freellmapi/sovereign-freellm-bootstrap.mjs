import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const SECRET_ROOT = '/run/secrets/freellm-provider-keys';
const RUNTIME_UID = 1000;
const RUNTIME_GID = 1000;
const providerPattern = /^[a-z][a-z0-9-]{1,31}$/;
const appliedFingerprints = new Map();

if (process.getuid() !== RUNTIME_UID || process.getgid() !== RUNTIME_GID) {
  throw new Error('freellm bootstrap runtime identity invalid');
}

function safeEntries() {
  let names = [];
  try {
    names = fs.readdirSync(SECRET_ROOT);
  } catch (error) {
    if (error && error.code === 'ENOENT') return [];
    throw error;
  }
  const entries = [];
  for (const name of names.sort()) {
    const match = /^([a-z][a-z0-9-]{1,31})\.(key|keyless)$/.exec(name);
    if (!match || !providerPattern.test(match[1])) continue;
    const filePath = path.join(SECRET_ROOT, name);
    const info = fs.lstatSync(filePath);
    if (!info.isFile() || info.isSymbolicLink() || (info.mode & 0o077) !== 0) {
      throw new Error(`invalid provider secret contract: ${name}`);
    }
    if (info.size < 1 || info.size > 8192) {
      throw new Error(`invalid provider secret size: ${name}`);
    }
    const protectedValue = Buffer.from(fs.readFileSync(filePath));
    try {
      const value = protectedValue.toString('utf8').trim();
      if (!value || /[\0\r\n]/.test(value)) {
        throw new Error(`invalid provider secret value: ${name}`);
      }
      const fingerprint = crypto.createHash('sha256').update(protectedValue).digest('hex');
      entries.push({
        fingerprint,
        input: {
          platform: match[1],
          key: match[2] === 'keyless' ? undefined : value,
          label: match[2] === 'keyless' ? 'sovereign-keyless' : 'sovereign-owner',
          enabled: true,
        },
      });
    } finally {
      protectedValue.fill(0);
    }
  }
  return entries;
}

const initialEntries = safeEntries();
let initialConfigPath = '';
if (initialEntries.length) {
  initialConfigPath = `/tmp/sovereign-freellm-provider-config-${process.pid}.json`;
  fs.writeFileSync(
    initialConfigPath,
    JSON.stringify({ keys: initialEntries.map(entry => entry.input) }),
    { encoding: 'utf8', mode: 0o600, flag: 'wx' },
  );
  process.env.FREEAPI_CONFIG_PATH = initialConfigPath;
  for (const entry of initialEntries) {
    appliedFingerprints.set(entry.input.platform, entry.fingerprint);
  }
}

await import('/app/server/dist/index.js');
const { applyDeclarativeConfig } = await import('/app/server/dist/services/declarative-config.js');
const { getDb } = await import('/app/server/dist/db/index.js');

function cleanupInitialConfigWhenReady() {
  if (!initialConfigPath) return;
  try {
    getDb();
  } catch {
    return;
  }
  fs.rmSync(initialConfigPath, { force: true });
  initialConfigPath = '';
  delete process.env.FREEAPI_CONFIG_PATH;
}

function syncProviderKeys() {
  const changed = [];
  for (const entry of safeEntries()) {
    const provider = entry.input.platform;
    if (appliedFingerprints.get(provider) === entry.fingerprint) continue;
    changed.push(entry.input);
    appliedFingerprints.set(provider, entry.fingerprint);
  }
  if (!changed.length) return;
  const result = applyDeclarativeConfig({ keys: changed }, 'sovereign-owner-secret-files');
  process.stdout.write(JSON.stringify({
    status: 'SOVEREIGN_FREELLM_PROVIDER_KEYS_IMPORTED',
    keyCount: result.keys,
    rawCredentialsReturned: false,
  }) + '\n');
}

setInterval(() => {
  try {
    cleanupInitialConfigWhenReady();
    syncProviderKeys();
  } catch (error) {
    process.stderr.write(JSON.stringify({
      status: 'SOVEREIGN_FREELLM_PROVIDER_KEY_SYNC_FAILED',
      errorFamily: error && error.code ? String(error.code).slice(0, 80) : 'provider_key_sync_failed',
      rawCredentialsReturned: false,
    }) + '\n');
  }
}, 15_000).unref();
