export type SovereignSideMenuDraftPrAction =
  | 'open-repo-setup'
  | 'open-github-access'
  | 'publish-draft-pr'
  | 'none';

export type SovereignSideMenuDraftPrState =
  | 'repo-required'
  | 'evidence-required'
  | 'access-required'
  | 'ready'
  | 'publishing'
  | 'already-exists';

export interface SovereignSideMenuDraftPrInput {
  readonly repoReady: boolean;
  readonly hasChangeEvidence: boolean;
  readonly githubWriteReady: boolean;
  readonly isPublishing: boolean;
  readonly draftPrUrl?: string | null;
}

export interface SovereignSideMenuDraftPrDecision {
  readonly state: SovereignSideMenuDraftPrState;
  readonly action: SovereignSideMenuDraftPrAction;
  readonly canAct: boolean;
  readonly label: string;
  readonly statusLabel: string;
  readonly reason: string;
}

export interface SovereignSideMenuShareDecision {
  readonly canShare: boolean;
  readonly statusLabel: string;
  readonly reason: string;
}

export function decideSovereignSideMenuDraftPr(
  input: SovereignSideMenuDraftPrInput,
): SovereignSideMenuDraftPrDecision {
  if (input.isPublishing) {
    return {
      state: 'publishing',
      action: 'none',
      canAct: false,
      label: 'Draft PR wird vorbereitet…',
      statusLabel: 'Runtime arbeitet',
      reason: 'Eine Draft-PR-Anfrage läuft bereits. Es wird kein zweiter Vorgang gestartet.',
    };
  }

  if (input.draftPrUrl?.trim()) {
    return {
      state: 'already-exists',
      action: 'none',
      canAct: false,
      label: 'Draft PR vorhanden',
      statusLabel: 'Bereits erstellt',
      reason: 'Für das geladene Repository ist bereits eine bestätigte Draft-PR-URL vorhanden.',
    };
  }

  if (!input.repoReady) {
    return {
      state: 'repo-required',
      action: 'open-repo-setup',
      canAct: true,
      label: 'Repo für Draft PR laden',
      statusLabel: 'Repo fehlt',
      reason: 'Ein Draft PR darf erst nach einem vollständigen Builder-Repo-Snapshot vorbereitet werden.',
    };
  }

  if (!input.hasChangeEvidence) {
    return {
      state: 'evidence-required',
      action: 'none',
      canAct: false,
      label: 'Draft PR noch nicht möglich',
      statusLabel: 'Patch/Diff fehlt',
      reason: 'Es gibt noch keine bestätigte Changed-Files- oder Patch-Diff-Evidence.',
    };
  }

  if (!input.githubWriteReady) {
    return {
      state: 'access-required',
      action: 'open-github-access',
      canAct: true,
      label: 'GitHub-Zugang für Draft PR',
      statusLabel: 'Schreibzugang fehlt',
      reason: 'Änderungs-Evidence ist vorhanden, aber der GitHub-Schreibzugang ist noch nicht validiert.',
    };
  }

  return {
    state: 'ready',
    action: 'publish-draft-pr',
    canAct: true,
    label: 'Draft PR vorbereiten',
    statusLabel: 'Startklar',
    reason: 'Repo, Änderungs-Evidence und GitHub-Schreibzugang sind bestätigt.',
  };
}

export function decideSovereignSideMenuShare(
  chatHistoryCount: number,
): SovereignSideMenuShareDecision {
  const normalizedCount = Number.isFinite(chatHistoryCount)
    ? Math.max(0, Math.floor(chatHistoryCount))
    : 0;

  if (normalizedCount === 0) {
    return {
      canShare: false,
      statusLabel: 'Noch leer',
      reason: 'Es gibt noch keinen gespeicherten Chat-Verlauf zum Exportieren.',
    };
  }

  return {
    canShare: true,
    statusLabel: `${normalizedCount} Nachricht${normalizedCount === 1 ? '' : 'en'}`,
    reason: 'Gespeicherter Chat-Verlauf ist vorhanden und kann geteilt oder kopiert werden.',
  };
}
