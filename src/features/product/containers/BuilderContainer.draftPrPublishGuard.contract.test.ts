import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/features/product/containers/BuilderContainer.tsx'), 'utf8');

describe('BuilderContainer Draft-PR publish guard contract', () => {
  it('holds a synchronous single-flight lock around the asynchronous Draft-PR publish', () => {
    const wrapperStart = source.indexOf('const publishConfirmedDraftPr = async (): Promise<void> => {');
    const innerStart = source.indexOf('const publishConfirmedDraftPrInner = async (): Promise<void> => {', wrapperStart);

    expect(wrapperStart).toBeGreaterThanOrEqual(0);
    expect(innerStart).toBeGreaterThan(wrapperStart);

    const wrapper = source.slice(wrapperStart, innerStart);
    const guard = wrapper.indexOf('if (publishDraftPrInFlightRef.current)');
    const acquire = wrapper.indexOf('publishDraftPrInFlightRef.current = true');
    const invoke = wrapper.indexOf('await publishConfirmedDraftPrInner()');
    const release = wrapper.indexOf('publishDraftPrInFlightRef.current = false');

    expect(guard).toBeGreaterThanOrEqual(0);
    expect(acquire).toBeGreaterThan(guard);
    expect(invoke).toBeGreaterThan(acquire);
    expect(wrapper).toContain('finally');
    expect(release).toBeGreaterThan(invoke);
  });

  it('wires DraftPrCard through the fail-closed build-status resolver', () => {
    expect(source).toContain('import { resolveDraftPrBuildStatus } from "../runtime/draftPrBuildStatusRuntime";');
    expect(source).toContain('buildStatus={resolveDraftPrBuildStatus({');
    expect(source).toContain('draftPrUrl: scopedAgentJob.draftPrUrl');
  });
});
