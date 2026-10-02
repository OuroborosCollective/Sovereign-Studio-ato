// Import the actual scanner as a module; isolate only its filesystem/report adapters.
import fs from 'node:fs';
import { describe, expect, it, vi } from 'vitest';

const commandSurfacePath = 'src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx';
const commandSurface = fs.readFileSync(commandSurfacePath, 'utf8');
const scannerPath = '../../../../scripts/sovereign-ux-contract-scan.mjs';

async function scan(overrides: Record<string, string> = {}) {
  let report: { status: string; errors: Array<{ id: string }> } | undefined;
  const exits: number[] = [];
  vi.resetModules();
  vi.doMock('node:fs', () => ({
    default: {
      ...fs,
      readFileSync: (filePath: string) => Object.prototype.hasOwnProperty.call(overrides, filePath)
        ? overrides[filePath] : fs.readFileSync(filePath, 'utf8'),
      mkdirSync: () => undefined,
      writeFileSync: () => undefined,
      appendFileSync: () => undefined,
    },
  }));
  vi.doMock('node:process', () => ({
    default: { env: {}, exit: (code: number) => { exits.push(code); } },
  }));
  const log = vi.spyOn(console, 'log').mockImplementation((value: string) => {
    report = JSON.parse(value);
  });
  try {
    await import(/* @vite-ignore */ scannerPath);
    if (!report) throw new Error('Scanner did not emit its report');
    return { report, exits };
  } finally {
    log.mockRestore();
    vi.doUnmock('node:fs');
    vi.doUnmock('node:process');
    vi.resetModules();
  }
}

describe('production UX scanner vNext bindings', () => {
  it('accepts the actual vNext command surface and production truth boundary', async () => {
    const { report, exits } = await scan();
    expect(report.status).toBe('pass');
    expect(report.errors).toEqual([]);
    expect(exits).toEqual([]);
  });

  it('rejects integration rows whose server provenance is disconnected', async () => {
    const path = 'src/features/control-surface-vnext/components/IntegrationPlus/IntegrationModal.tsx';
    const source = fs.readFileSync(path, 'utf8');
    const broken = source.replace('item.readbackSha256', 'item.syntheticHash');
    expect(broken).not.toBe(source);
    const { report, exits } = await scan({ [path]: broken });
    expect(report.errors.map(error => error.id)).toContain('integration:provenance');
    expect(exits).toEqual([1]);
  });

  it('rejects integrations disconnected from the real backend contract', async () => {
    const path = 'src/features/control-surface-vnext/adapter/production-adapter.ts';
    const source = fs.readFileSync(path, 'utf8');
    const broken = source.replace('/api/user/agent/control-surface', '/api/unsupported/invented-integrations');
    expect(broken).not.toBe(source);
    const { report, exits } = await scan({ [path]: broken });
    expect(report.errors.map(error => error.id)).toContain('integration:server-contract');
    expect(exits).toEqual([1]);
  });

  it('rejects a changed visible dispatch handler even when submit still exists elsewhere', async () => {
    const broken = commandSurface.replace(
      'onClick={submit}',
      'onClick={() => unrelatedHandler()}',
    );
    expect(broken).not.toBe(commandSurface);
    const { report, exits } = await scan({ [commandSurfacePath]: broken });
    expect(report.errors.map(error => error.id)).toContain('surface:send-visible');
    expect(exits).toEqual([1]);
  });

  it('rejects a composer disconnected from the command draft state', async () => {
    const broken = commandSurface.replace(
      'onChange={(event) => { setText(event.target.value);',
      'onChange={(event) => { unrelatedHandler(event.target.value);',
    );
    expect(broken).not.toBe(commandSurface);
    const { report, exits } = await scan({ [commandSurfacePath]: broken });
    expect(report.errors.map(error => error.id)).toContain('surface:composer-bound');
    expect(exits).toEqual([1]);
  });
});
