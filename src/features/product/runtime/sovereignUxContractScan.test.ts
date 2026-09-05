// Execute the actual scanner; only filesystem/report/process adapters are isolated.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const builderPath = 'src/features/product/containers/BuilderContainer.tsx';
const builder = fs.readFileSync(builderPath, 'utf8');
const scanner = fs.readFileSync('scripts/sovereign-ux-contract-scan.mjs', 'utf8')
  .replace(/^import .+;$/gm, '');

function scan(source: string) {
  let report: { status: string; errors: Array<{ id: string }> } | undefined;
  const exits: number[] = [];
  vm.runInNewContext(scanner, {
    fs: {
      ...fs,
      readFileSync: (filePath: string) => filePath === builderPath
        ? source : fs.readFileSync(filePath, 'utf8'),
      mkdirSync: () => undefined,
      writeFileSync: () => undefined,
      appendFileSync: () => undefined,
    },
    path,
    process: { env: {}, exit: (code: number) => { exits.push(code); } },
    console: { log: (value: string) => { report = JSON.parse(value); } },
  }, { timeout: 5000 });
  if (!report) throw new Error('Scanner did not emit its report');
  return { report, exits };
}

describe('production UX scanner chat bindings', () => {
  it('accepts the actual chat dock with its expanded empty-state markup', () => {
    const { report, exits } = scan(builder);
    expect(report.status).toBe('pass');
    expect(report.errors).toEqual([]);
    expect(exits).toEqual([]);
  });

  it('rejects a changed submit handler even when the original name remains elsewhere', () => {
    const broken = builder.replace('onSubmit={() => { void handleSubmit(); }}',
      'onSubmit={() => { void unrelatedHandler(); }}');
    expect(broken).not.toBe(builder);
    const { report, exits } = scan(broken);
    expect(report.errors.map(error => error.id)).toContain('builder:start-visible');
    expect(exits).toEqual([1]);
  });

  it('rejects an input state disconnected from setWishText', () => {
    const broken = builder.replace('onChange={setWishText}', 'onChange={unrelatedHandler}');
    expect(broken).not.toBe(builder);
    const { report, exits } = scan(broken);
    expect(report.errors.map(error => error.id)).toContain('builder:mission-form-bound');
    expect(exits).toEqual([1]);
  });
});
