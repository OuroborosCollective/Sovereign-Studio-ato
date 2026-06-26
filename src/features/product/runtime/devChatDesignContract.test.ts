import { describe, expect, it } from 'vitest';
import {
  SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT,
  assertDevChatDesignContractValid,
  validateDevChatDesignContract,
  type DevChatDesignContract,
} from './devChatDesignContract';

describe('devChatDesignContract', () => {
  it('keeps the approved DevChat structure locked', () => {
    const report = validateDevChatDesignContract();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
    expect(SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT.structureLocked).toBe(true);
    expect(SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT.centralBodyWidthPercent).toBe(55);
    expect(SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT.composerWidthPercentOfBody).toBe(80);
    expect(SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT.maxSideMenuOverlayPercentOfBody).toBe(10);
  });

  it('requires the exact slot order from the approved design', () => {
    expect(SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT.slots.map((slot) => slot.id)).toEqual([
      'status-bar',
      'message-scroll-body',
      'input-bar',
      'runtime-source-sheet',
      'side-menu-drawer',
    ]);
  });

  it('rejects structural drift', () => {
    const drifted: DevChatDesignContract = {
      ...SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT,
      centralBodyWidthPercent: 60,
      maxSideMenuOverlayPercentOfBody: 25,
    };

    const report = validateDevChatDesignContract(drifted);

    expect(report.valid).toBe(false);
    expect(report.errors.join(' | ')).toContain('Central chat body width must stay at 55 percent.');
    expect(report.errors.join(' | ')).toContain('Side menu overlay must not exceed 10 percent');
  });

  it('throws with a clear reason when the contract is invalid', () => {
    expect(() => assertDevChatDesignContractValid({
      ...SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT,
      structureLocked: false as true,
    })).toThrow('DevChat design structure must remain locked.');
  });
});
