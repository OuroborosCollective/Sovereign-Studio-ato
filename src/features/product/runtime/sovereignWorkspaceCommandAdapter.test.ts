import { describe, expect, it } from 'vitest';
import { normalizeSovereignWorkspaceCommandAdapterInput } from './sovereignWorkspaceCommandAdapter';

describe('sovereignWorkspaceCommandAdapter', () => {
  it('accepts only the normalized workspace command contract shape', () => {
    expect(normalizeSovereignWorkspaceCommandAdapterInput({ targetTab: 'repo', type: 'next' })).toEqual({ targetTab: 'repo', type: 'next' });
    expect(normalizeSovereignWorkspaceCommandAdapterInput({ targetTab: 'runtime', type: 'confirm' })).toEqual({ targetTab: 'runtime', type: 'confirm' });
    expect(normalizeSovereignWorkspaceCommandAdapterInput({ targetTab: 'unknown-area', type: 'next' })).toBeNull();
    expect(normalizeSovereignWorkspaceCommandAdapterInput({ tab: 'repo', type: 'next' })).toBeNull();
    expect(normalizeSovereignWorkspaceCommandAdapterInput(null)).toBeNull();
  });
});
