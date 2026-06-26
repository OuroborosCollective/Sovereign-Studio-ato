/**
 * Dev Chat Design Contract
 *
 * This is the fixed visual structure contract derived from the approved DevChat reference.
 * Runtime code may wire real data into these slots, but must not replace the structure.
 */

export type DevChatDesignSlot =
  | 'status-bar'
  | 'message-scroll-body'
  | 'input-bar'
  | 'runtime-source-sheet'
  | 'side-menu-drawer';

export interface DevChatDesignSlotContract {
  readonly id: DevChatDesignSlot;
  readonly order: number;
  readonly required: boolean;
  readonly purpose: string;
}

export interface DevChatDesignContract {
  readonly version: 1;
  readonly name: 'Sovereign DevChat Shell';
  readonly structureLocked: true;
  readonly centralBodyWidthPercent: 55;
  readonly composerWidthPercentOfBody: 80;
  readonly maxSideMenuOverlayPercentOfBody: 10;
  readonly slots: readonly DevChatDesignSlotContract[];
  readonly invariants: readonly string[];
}

export interface DevChatDesignValidationReport {
  readonly valid: boolean;
  readonly errors: readonly string[];
  readonly summary: string;
}

export const SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT: DevChatDesignContract = {
  version: 1,
  name: 'Sovereign DevChat Shell',
  structureLocked: true,
  centralBodyWidthPercent: 55,
  composerWidthPercentOfBody: 80,
  maxSideMenuOverlayPercentOfBody: 10,
  slots: [
    {
      id: 'status-bar',
      order: 0,
      required: true,
      purpose: 'Top runtime status, repo state and active runtime source.',
    },
    {
      id: 'message-scroll-body',
      order: 1,
      required: true,
      purpose: 'Central scrollable chat content window for user, assistant, thought and system lines.',
    },
    {
      id: 'input-bar',
      order: 2,
      required: true,
      purpose: 'Bottom composer with menu button, text input and send action.',
    },
    {
      id: 'runtime-source-sheet',
      order: 3,
      required: true,
      purpose: 'Overlay sheet for real runtime source status; it must not fabricate model availability.',
    },
    {
      id: 'side-menu-drawer',
      order: 4,
      required: true,
      purpose: 'Small overlay drawer for secondary menus and diagnostics.',
    },
  ],
  invariants: [
    'The top-level layout is status bar, scrollable message body and bottom input bar.',
    'The message body remains the central visual area and uses a 55 percent desktop body width contract.',
    'The composer is directly below the message body and uses an 80 percent body-width contract on desktop.',
    'Side menus are overlays or rails; they must not replace the central chat body.',
    'A side menu overlay may cover at most 10 percent of the chat body on desktop, with a mobile usability exception.',
    'Runtime wiring may change text and state, but it must not introduce demo conversations, fake messages or simulated agent replies.',
    'The design structure may not be replaced by cards, dashboard grids or a second chat surface.',
  ],
};

export function validateDevChatDesignContract(
  contract: DevChatDesignContract = SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT,
): DevChatDesignValidationReport {
  const errors: string[] = [];
  const requiredOrder: readonly DevChatDesignSlot[] = [
    'status-bar',
    'message-scroll-body',
    'input-bar',
    'runtime-source-sheet',
    'side-menu-drawer',
  ];

  if (contract.version !== 1) errors.push('DevChat design contract version must be 1.');
  if (contract.name !== 'Sovereign DevChat Shell') errors.push('DevChat design contract name changed.');
  if (!contract.structureLocked) errors.push('DevChat design structure must remain locked.');
  if (contract.centralBodyWidthPercent !== 55) errors.push('Central chat body width must stay at 55 percent.');
  if (contract.composerWidthPercentOfBody !== 80) errors.push('Composer width must stay at 80 percent of the chat body.');
  if (contract.maxSideMenuOverlayPercentOfBody > 10) errors.push('Side menu overlay must not exceed 10 percent of the chat body on desktop.');

  const orderedSlots = [...contract.slots].sort((a, b) => a.order - b.order).map((slot) => slot.id);
  if (orderedSlots.join('>') !== requiredOrder.join('>')) {
    errors.push(`DevChat slot order changed: ${orderedSlots.join(' > ')}`);
  }

  for (const slot of requiredOrder) {
    const match = contract.slots.find((candidate) => candidate.id === slot);
    if (!match) errors.push(`Missing DevChat slot: ${slot}`);
    else if (!match.required) errors.push(`Required DevChat slot marked optional: ${slot}`);
  }

  return {
    valid: errors.length === 0,
    errors,
    summary: `${errors.length} DevChat design contract error(s).`,
  };
}

export function assertDevChatDesignContractValid(contract: DevChatDesignContract = SOVEREIGN_DEV_CHAT_DESIGN_CONTRACT): void {
  const report = validateDevChatDesignContract(contract);
  if (!report.valid) throw new Error(`DevChat design contract invalid: ${report.errors.join(' | ')}`);
}
