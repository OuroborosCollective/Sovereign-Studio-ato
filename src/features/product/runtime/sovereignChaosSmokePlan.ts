export type SovereignChaosTarget = 'tab-boundary' | 'dependency-lifecycle' | 'workflow-watch' | 'remote-memory';
export type SovereignChaosExpectedResult = 'fallback-rendered' | 'circuit-opened' | 'telemetry-emitted' | 'coach-signal-emitted' | 'main-flow-still-usable';

export interface SovereignChaosSmokeStep {
  id: string;
  target: SovereignChaosTarget;
  action: string;
  expected: SovereignChaosExpectedResult[];
  liveSafe: boolean;
}

export interface SovereignChaosSmokePlan {
  id: string;
  title: string;
  enabledInLivePath: false;
  steps: SovereignChaosSmokeStep[];
}

function assertStepValid(step: SovereignChaosSmokeStep): void {
  if (!step.id.trim()) throw new Error('Chaos smoke step id is required.');
  if (!step.action.trim()) throw new Error(`Chaos smoke step ${step.id} action is required.`);
  if (!step.expected.length) throw new Error(`Chaos smoke step ${step.id} needs expected results.`);
  if (!step.liveSafe) throw new Error(`Chaos smoke step ${step.id} must be marked liveSafe=false or kept outside live runtime.`);
}

export function createSovereignChaosSmokePlan(): SovereignChaosSmokePlan {
  const plan: SovereignChaosSmokePlan = {
    id: 'sovereign-chaos-smoke-tab-and-dependency-circuit',
    title: 'Sovereign chaos smoke for tab fallback and dependency circuit lifecycle',
    enabledInLivePath: false,
    steps: [
      {
        id: 'tab-crash-isolated',
        target: 'tab-boundary',
        action: 'Render a test-only throwing child inside SovereignTabErrorBoundary.',
        expected: ['fallback-rendered', 'telemetry-emitted', 'coach-signal-emitted', 'main-flow-still-usable'],
        liveSafe: true,
      },
      {
        id: 'tab-circuit-opens',
        target: 'tab-boundary',
        action: 'Repeat the same test-only tab crash until the circuit threshold is reached.',
        expected: ['fallback-rendered', 'circuit-opened', 'main-flow-still-usable'],
        liveSafe: true,
      },
      {
        id: 'dependency-circuit-recovers',
        target: 'dependency-lifecycle',
        action: 'Record dependency failures, wait cooldown in deterministic test time, then record a successful half-open probe.',
        expected: ['circuit-opened', 'telemetry-emitted', 'main-flow-still-usable'],
        liveSafe: true,
      },
    ],
  };

  assertSovereignChaosSmokePlan(plan);
  return plan;
}

export function assertSovereignChaosSmokePlan(plan: SovereignChaosSmokePlan): void {
  if (!plan.id.trim()) throw new Error('Chaos smoke plan id is required.');
  if (!plan.title.trim()) throw new Error('Chaos smoke plan title is required.');
  if (plan.enabledInLivePath !== false) throw new Error('Chaos smoke plan must stay disabled in the live path.');
  if (!plan.steps.length) throw new Error('Chaos smoke plan requires at least one step.');
  plan.steps.forEach(assertStepValid);
}

export function summarizeSovereignChaosSmokePlan(plan: SovereignChaosSmokePlan): string {
  assertSovereignChaosSmokePlan(plan);
  return `${plan.title}: ${plan.steps.length} safe test-only step(s), livePath=${String(plan.enabledInLivePath)}.`;
}
