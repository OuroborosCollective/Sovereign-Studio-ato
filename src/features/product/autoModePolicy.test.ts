import { describe, expect, it } from 'vitest';
import { decideAutoMode } from './autoModePolicy';

describe('autoModePolicy', () => {
  it('starts a visible fix when an error exists', () => {
    expect(decideAutoMode({ step: 'check', auto: false, hasError: true, green: false })).toBe('run-fix');
  });

  it('prepares write only in auto mode and green state', () => {
    expect(decideAutoMode({ step: 'check', auto: true, hasError: false, green: true })).toBe('prepare-write');
  });
});
