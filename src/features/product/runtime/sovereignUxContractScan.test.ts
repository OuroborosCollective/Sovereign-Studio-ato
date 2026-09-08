// Import the actual scanner as a module; isolate only its filesystem/report adapters.
import fs from 'node:fs';
import { describe, expect, it, vi } from 'vitest';

const releasePath = 'src/features/release/PlayReleaseChat.tsx';
const release = fs.readFileSync(releasePath, 'utf8');
const scannerPath = '../../../../scripts/sovereign-ux-contract-scan.mjs';

async function scan(source: string) {
  let report: { status: string; errors: Array<{ id: string }> } | undefined;
  const exits: number[] = [];
  vi.resetModules();
  vi.doMock('node:fs', () => ({
    default: {
      ...fs,
      readFileSync: (filePath: string) => filePath === releasePath
        ? source : fs.readFileSync(filePath, 'utf8'),
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

describe('production UX scanner current-session bindings', () => {
  it('accepts the actual Play Release composer and guarded submit path', async () => {
    const { report, exits } = await scan(release);
    expect(report.status).toBe('pass');
    expect(report.errors).toEqual([]);
    expect(exits).toEqual([]);
  });

  it('rejects a changed visible send handler even when submit still exists elsewhere', async () => {
    const broken = release.replace(
      'onClick={() => { void submit(); }}',
      'onClick={() => { void unrelatedHandler(); }}',
    );
    expect(broken).not.toBe(release);
    const { report, exits } = await scan(broken);
    expect(report.errors.map(error => error.id)).toContain('release:send-visible');
    expect(exits).toEqual([1]);
  });

  it('rejects a composer disconnected from the current-session draft state', async () => {
    const broken = release.replace(
      'onChange={(event) => setDraft(event.target.value)}',
      'onChange={(event) => unrelatedHandler(event.target.value)}',
    );
    expect(broken).not.toBe(release);
    const { report, exits } = await scan(broken);
    expect(report.errors.map(error => error.id)).toContain('release:composer-bound');
    expect(exits).toEqual([1]);
  });
});
