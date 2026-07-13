/**
 * Sovereign preset actions define fixed, guided repo tasks shown in the chat.
 * UI only displays these actions; route truth, gates and prompts live here.
 */

export type SovereignPresetActionId =
  | 'architecture_feature_suggestions'
  | 'error_fix_plan'
  | 'docs_architecture_sync'
  | 'runtime_hardening'
  | 'tests_gate_repair'
  | 'open_pr_review';

export type SovereignPresetRoute =
  | 'worker_analysis'
  | 'direct_patch_or_agent'
  | 'agent_or_plan'
  | 'runtime_review';

export type SovereignPresetRisk = 'safe_analysis' | 'reviewable_patch' | 'executor_required';

export interface SovereignPresetAction {
  readonly id: SovereignPresetActionId;
  readonly icon: string;
  readonly label: string;
  readonly shortLabel: string;
  readonly description: string;
  readonly requiresRepo: boolean;
  readonly requiresGithubWrite: boolean;
  readonly route: SovereignPresetRoute;
  readonly risk: SovereignPresetRisk;
  readonly prompt: string;
}

export interface SovereignPresetActionContext {
  readonly repoReady: boolean;
  readonly repoFullName?: string | null;
  readonly branch?: string | null;
  readonly githubWriteReady?: boolean;
  readonly agentReady?: boolean;
}

export interface SovereignPresetActionGate {
  readonly actionId: SovereignPresetActionId;
  readonly canStart: boolean;
  readonly reason: string;
  readonly nextAction: string;
}

export const SOVEREIGN_PRESET_ACTIONS: readonly SovereignPresetAction[] = [
  {
    id: 'architecture_feature_suggestions',
    icon: '✨',
    label: 'Feature-Vorschläge aus Architektur',
    shortLabel: 'Features',
    description: 'Repo-Struktur lesen und nützliche, kleine Produktverbesserungen vorschlagen.',
    requiresRepo: true,
    requiresGithubWrite: false,
    route: 'worker_analysis',
    risk: 'safe_analysis',
    prompt: [
      'Analysiere die aktuelle Repo-Architektur und schlage mir kleine, nützliche Feature-Verbesserungen vor.',
      'Nur Analyse. Repo nur lesen. Kein PR-Vorgang starten.',
      'Sortiere nach Wirkung, Risiko und nächstem Runtime-Gate.',
    ].join('\n'),
  },
  {
    id: 'error_fix_plan',
    icon: '🛠',
    label: 'Fehler suchen & Fixplan',
    shortLabel: 'Fehler',
    description: 'Aktuelle Stopper, Worker-/Runtime-Blocker und wahrscheinliche Ursachen strukturieren.',
    requiresRepo: true,
    requiresGithubWrite: false,
    route: 'worker_analysis',
    risk: 'safe_analysis',
    prompt: [
      'Suche im aktuellen Repo-Kontext nach wahrscheinlichen Fehlerquellen und erstelle einen Fixplan.',
      'Nur Analyse. Erst Ursache, dann Fix-Reihenfolge, dann Tests nennen. Repo nur lesen.',
    ].join('\n'),
  },
  {
    id: 'docs_architecture_sync',
    icon: '📘',
    label: 'README & Docs aktualisieren',
    shortLabel: 'Docs',
    description: 'README/docs mit der echten aktuellen Architektur abgleichen und Patch vorbereiten.',
    requiresRepo: true,
    requiresGithubWrite: true,
    route: 'direct_patch_or_agent',
    risk: 'reviewable_patch',
    prompt: [
      'Aktualisiere README und docs anhand der aktuellen echten Architektur.',
      'Erzeuge zuerst einen prüfbaren Direct-Patch-Diff. Veröffentlichung erst nach bestätigtem Diff; kein Auto-Merge.',
      'Keine erfundenen Features dokumentieren.',
    ].join('\n'),
  },
  {
    id: 'runtime_hardening',
    icon: '🧱',
    label: 'Runtime härten',
    shortLabel: 'Runtime',
    description: 'Runtime-Gates, Validierung, State-Übergänge und Blocker prüfen.',
    requiresRepo: true,
    requiresGithubWrite: false,
    route: 'runtime_review',
    risk: 'safe_analysis',
    prompt: [
      'Prüfe die Runtime-Architektur auf fehlende Gates, Validierungen und instabile State-Übergänge.',
      'Nur Analyse. Liefere konkrete Härtungsmaßnahmen mit Tests. Repo nur lesen.',
    ].join('\n'),
  },
  {
    id: 'tests_gate_repair',
    icon: '✅',
    label: 'Tests & Gates reparieren',
    shortLabel: 'Gates',
    description: 'Typecheck, Tests, E2E und Contract-Scans als Reparaturpfad behandeln.',
    requiresRepo: true,
    requiresGithubWrite: true,
    route: 'agent_or_plan',
    risk: 'executor_required',
    prompt: [
      'Repariere rote Tests, Typecheck, E2E oder Contract-Scans im Repo.',
      'Arbeite nur über prüfbaren Patch/Draft PR. Kein Auto-Merge.',
      'Jeder Fix braucht einen passenden Test oder Gate-Beweis.',
    ].join('\n'),
  },
  {
    id: 'open_pr_review',
    icon: '🔎',
    label: 'Offene PRs prüfen',
    shortLabel: 'PRs',
    description: 'Offene PRs auf Scope, Artefakte, Mergebarkeit und Gate-Risiken bewerten.',
    requiresRepo: true,
    requiresGithubWrite: false,
    route: 'runtime_review',
    risk: 'safe_analysis',
    prompt: [
      'Prüfe offene Reviewstände im aktuellen Repo.',
      'Bewerte Scope, generierte Artefakte, Mergebarkeit, Checks und Blocker.',
      'Keine PR mergen und nichts schließen ohne ausdrückliche Freigabe.',
    ].join('\n'),
  },
] as const;

export function getSovereignPresetAction(id: SovereignPresetActionId): SovereignPresetAction {
  const action = SOVEREIGN_PRESET_ACTIONS.find((item) => item.id === id);
  if (!action) throw new Error(`Unknown Sovereign preset action: ${id}`);
  return action;
}

export function evaluateSovereignPresetActionGate(
  action: SovereignPresetAction,
  context: SovereignPresetActionContext,
): SovereignPresetActionGate {
  if (action.requiresRepo && !context.repoReady) {
    return {
      actionId: action.id,
      canStart: false,
      reason: 'Repo-Kontext fehlt.',
      nextAction: 'Bitte zuerst eine GitHub-Repo-URL laden.',
    };
  }
  if (action.requiresGithubWrite && !context.githubWriteReady) {
    return {
      actionId: action.id,
      canStart: false,
      reason: 'GitHub-Schreibzugang fehlt.',
      nextAction: 'Sicheren GitHub-Zugang öffnen; der vorgemerkte Auftrag läuft danach automatisch weiter.',
    };
  }
  return {
    actionId: action.id,
    canStart: true,
    reason: 'Preset-Aktion ist startklar.',
    nextAction: action.risk === 'safe_analysis' ? 'Analyse starten.' : 'Patch/Draft-PR Gate prüfen.',
  };
}

export function buildSovereignPresetActionPrompt(
  action: SovereignPresetAction,
  context: SovereignPresetActionContext,
): string {
  const repoLine = context.repoFullName
    ? `Repo: ${context.repoFullName}${context.branch ? ` · Branch: ${context.branch}` : ''}`
    : 'Repo: noch nicht geladen';
  const routeLine = `Preset-Route: ${action.route} · Risiko: ${action.risk}`;
  const gateParts = [
    `Repo geladen: ${context.repoReady ? 'ja' : 'nein'}`,
    action.requiresGithubWrite && !context.githubWriteReady
      ? 'GitHub Write: wird vor Ausführung geprüft'
      : `GitHub Write: ${context.githubWriteReady ? 'ja' : 'nein'}`,
  ];

  if (action.risk !== 'safe_analysis') {
    gateParts.push(`Sovereign Agent: ${context.agentReady ? 'bereit' : 'nicht bereit'}`);
  }

  return [
    `Sovereign Preset: ${action.label}`,
    repoLine,
    routeLine,
    gateParts.join(' · '),
    '',
    action.prompt,
  ].join('\n');
}

export function buildSovereignPresetActionSubmission(
  action: SovereignPresetAction,
  context: SovereignPresetActionContext,
): string {
  const prompt = buildSovereignPresetActionPrompt(action, context);
  if (action.risk !== 'safe_analysis') return prompt;

  return [
    'Was ist die sichere Analyse für dieses Repo?',
    prompt,
    '',
    'Preset-Ausführungsmodus: safe_analysis.',
    'Diese Aktion ist eine Beratungs-/Runtime-Analyse. Sie darf keinen Executor starten und keinen GitHub-Schreibzugang verlangen.',
  ].join('\n');
}
