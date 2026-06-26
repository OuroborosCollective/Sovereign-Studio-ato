import { describe, expect, it } from 'vitest';
import {
  SOVEREIGN_CONTROL_FRAME_CONTRACT,
  validateSovereignControlFrameContract,
} from './sovereignControlFrameContract';

describe('sovereignControlFrameContract', () => {
  it('keeps chat workbench as the fixed center slot', () => {
    const report = validateSovereignControlFrameContract();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
    expect(SOVEREIGN_CONTROL_FRAME_CONTRACT.centerSlot).toBe('center-chat-workbench');
    expect(SOVEREIGN_CONTROL_FRAME_CONTRACT.maxMobileWidthDp).toBe(393);
  });

  it('keeps all control modules as menu-only inspectors', () => {
    expect(SOVEREIGN_CONTROL_FRAME_CONTRACT.modules.map((module) => module.id)).toEqual([
      'init',
      'router',
      'pattern',
      'sync',
      'orchestr',
      'session',
      'logger',
      'restore',
    ]);
    expect(SOVEREIGN_CONTROL_FRAME_CONTRACT.modules.every((module) => module.menuOnly)).toBe(true);
  });
});
