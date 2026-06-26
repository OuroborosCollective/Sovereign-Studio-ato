/**
 * Sovereign Control Frame Contract
 *
 * AppControlScreen is accepted as a visual/runtime-inspector frame only.
 * The center slot is reserved for the existing DevChat/Chat Workbench.
 * No simulated timers, Math.random state, or UI-generated runtime truth are allowed.
 */

export type SovereignControlFrameSlot =
  | 'android-status-bar'
  | 'top-runtime-toolbar'
  | 'center-chat-workbench'
  | 'collapsible-runtime-panel'
  | 'bottom-runtime-nav';

export type SovereignControlFrameModuleId =
  | 'init'
  | 'router'
  | 'pattern'
  | 'sync'
  | 'orchestr'
  | 'session'
  | 'logger'
  | 'restore';

export type SovereignControlSignal = 'idle' | 'active' | 'processing' | 'warning' | 'error';
export type SovereignControlPhase = 'idle' | 'spinup' | 'working' | 'completing' | 'done' | 'error';
export type SovereignControlConditionStatus = 'pass' | 'fail' | 'wait';

export interface SovereignControlFrameSlotContract {
  readonly id: SovereignControlFrameSlot;
  readonly order: number;
  readonly required: true;
  readonly purpose: string;
}

export interface SovereignControlFrameModuleContract {
  readonly id: SovereignControlFrameModuleId;
  readonly label: string;
  readonly short: string;
  readonly runtimeSource: string;
  readonly menuOnly: boolean;
}

export interface SovereignControlFrameContract {
  readonly version: 1;
  readonly name: 'Sovereign Control Frame';
  readonly structureLocked: true;
  readonly centerSlot: 'center-chat-workbench';
  readonly maxMobileWidthDp: 393;
  readonly amoledBlack: '#000000';
  readonly slots: readonly SovereignControlFrameSlotContract[];
  readonly modules: readonly SovereignControlFrameModuleContract[];
  readonly invariants: readonly string[];
}

export interface SovereignControlFrameValidationReport {
  readonly valid: boolean;
  readonly errors: readonly string[];
  readonly summary: string;
}

export const SOVEREIGN_CONTROL_FRAME_CONTRACT: SovereignControlFrameContract = {
  version: 1,
  name: 'Sovereign Control Frame',
  structureLocked: true,
  centerSlot: 'center-chat-workbench',
  maxMobileWidthDp: 393,
  amoledBlack: '#000000',
  slots: [
    {
      id: 'android-status-bar',
      order: 0,
      required: true,
      purpose: 'Small Android-first status strip with real runtime summary only.',
    },
    {
      id: 'top-runtime-toolbar',
      order: 1,
      required: true,
      purpose: 'Current module, signal and override status derived from runtime state.',
    },
    {
      id: 'center-chat-workbench',
      order: 2,
      required: true,
      purpose: 'The existing Sovereign DevChat/Chat Workbench remains the main work surface.',
    },
    {
      id: 'collapsible-runtime-panel',
      order: 3,
      required: true,
      purpose: 'Optional inspector panel for logs, signals and session state from real telemetry.',
    },
    {
      id: 'bottom-runtime-nav',
      order: 4,
      required: true,
      purpose: 'Compact runtime module navigation; it is an inspector control, not a second main workflow.',
    },
  ],
  modules: [
    { id: 'init', label: 'INIT', short: 'INT', runtimeSource: 'repoSnapshotStatus/setupState', menuOnly: true },
    { id: 'router', label: 'ROUTER', short: 'ROU', runtimeSource: 'sovereignAutoViewRouter', menuOnly: true },
    { id: 'pattern', label: 'PATTERN', short: 'PAT', runtimeSource: 'solutionPatternStore', menuOnly: true },
    { id: 'sync', label: 'SYNC', short: 'SYN', runtimeSource: 'remoteMemoryConfig/remoteMemoryResults', menuOnly: true },
    { id: 'orchestr', label: 'ORCHESTR', short: 'ORC', runtimeSource: 'sequentialRuntime/openhandsJob', menuOnly: true },
    { id: 'session', label: 'SESSION', short: 'SES', runtimeSource: 'sovereignSessionMemory', menuOnly: true },
    { id: 'logger', label: 'LOGGER', short: 'LOG', runtimeSource: 'sovereignTelemetry', menuOnly: true },
    { id: 'restore', label: 'RESTORE', short: 'RST', runtimeSource: 'restoreRepoSnapshot/clearRepoSnapshot', menuOnly: true },
  ],
  invariants: [
    'The center slot must render the existing chat workbench and must not be replaced by AppControl tabs.',
    'The frame may display runtime state, but it must not create runtime truth.',
    'No Math.random, random signal drift, simulation interval, fake pattern commits or fake AutoSwitch logs are allowed in the live path.',
    'All control-frame module states must be derived from real Sovereign runtime inputs.',
    'The bottom runtime navigation is an inspector nav, not the primary product workflow.',
    'The approved DevChat design contract remains the user-facing workbench contract inside the frame.',
  ],
};

export function validateSovereignControlFrameContract(
  contract: SovereignControlFrameContract = SOVEREIGN_CONTROL_FRAME_CONTRACT,
): SovereignControlFrameValidationReport {
  const errors: string[] = [];
  const slotOrder: readonly SovereignControlFrameSlot[] = [
    'android-status-bar',
    'top-runtime-toolbar',
    'center-chat-workbench',
    'collapsible-runtime-panel',
    'bottom-runtime-nav',
  ];
  const moduleOrder: readonly SovereignControlFrameModuleId[] = [
    'init',
    'router',
    'pattern',
    'sync',
    'orchestr',
    'session',
    'logger',
    'restore',
  ];

  if (contract.version !== 1) errors.push('Control frame contract version must be 1.');
  if (contract.name !== 'Sovereign Control Frame') errors.push('Control frame name changed.');
  if (!contract.structureLocked) errors.push('Control frame structure must stay locked.');
  if (contract.centerSlot !== 'center-chat-workbench') errors.push('Center slot must remain the chat workbench.');
  if (contract.maxMobileWidthDp !== 393) errors.push('Android frame width contract must stay 393dp.');
  if (contract.amoledBlack !== '#000000') errors.push('AMOLED root background must remain true black.');

  const actualSlots = [...contract.slots].sort((a, b) => a.order - b.order).map((slot) => slot.id);
  if (actualSlots.join('>') !== slotOrder.join('>')) errors.push(`Control frame slot order changed: ${actualSlots.join(' > ')}`);

  const actualModules = contract.modules.map((module) => module.id);
  if (actualModules.join('>') !== moduleOrder.join('>')) errors.push(`Control frame module order changed: ${actualModules.join(' > ')}`);

  for (const module of contract.modules) {
    if (!module.menuOnly) errors.push(`Control frame module must stay menu-only: ${module.id}`);
    if (!module.runtimeSource.trim()) errors.push(`Control frame module missing runtime source: ${module.id}`);
  }

  return {
    valid: errors.length === 0,
    errors,
    summary: `${errors.length} control frame contract error(s).`,
  };
}

export function assertSovereignControlFrameContractValid(contract: SovereignControlFrameContract = SOVEREIGN_CONTROL_FRAME_CONTRACT): void {
  const report = validateSovereignControlFrameContract(contract);
  if (!report.valid) throw new Error(`Sovereign control frame contract invalid: ${report.errors.join(' | ')}`);
}
