// Import the actual scanner as a module; isolate only its filesystem/report adapters.
import fs from 'node:fs';
import { describe, expect, it, vi } from 'vitest';

const builderPath = 'src/features/product/containers/BuilderContainer.tsx';
const builder = fs.readFileSync(builderPath, 'utf8');
const scannerPath = '../../../../scripts/sovereign-ux-contract-scan.mjs';

async function scan(source: string) {
  let report: { status: string; errors: Array<{ id: string }> } | undefined;
  const exits: number[] = [];
  vi.resetModules();
  vi.doMock('node:fs', () => ({
    default: {
      ...fs,
      readFileSync: (filePath: string) => filePath === builderPath
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

describe('production UX scanner chat bindings', () => {
  it('accepts the actual chat dock with its expanded empty-state markup', async () => {
    const { report, exits } = await scan(builder);
    expect(report.status).toBe('pass');
    expect(report.errors).toEqual([]);
    expect(exits).toEqual([]);
  });

  it('rejects a changed submit handler even when the original name remains elsewhere', async () => {
    const broken = builder.replace('onSubmit={() => { void handleSubmit(); }}',
      'onSubmit={() => { void unrelatedHandler(); }}');
    expect(broken).not.toBe(builder);
    const { report, exits } = await scan(broken);
    expect(report.errors.map(error => error.id)).toContain('builder:start-visible');
    expect(exits).toEqual([1]);
  });

  it('rejects an input state disconnected from setWishText', async () => {
    const broken = builder.replace('onChange={setWishText}', 'onChange={unrelatedHandler}');
    expect(broken).not.toBe(builder);
    const { report, exits } = await scan(broken);
    expect(report.errors.map(error => error.id)).toContain('builder:mission-form-bound');
    expect(exits).toEqual([1]);
  });
});
