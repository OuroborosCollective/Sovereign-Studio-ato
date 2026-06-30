export type DraftPrBuildState = 'success' | 'failure' | 'running' | 'pending' | 'unknown';

export interface DraftPrWorkflowRunLike {
  readonly status?: string | null;
  readonly conclusion?: string | null;
  readonly html_url?: string | null;
}

export interface DraftPrBuildStatusInput {
  readonly draftPrUrl?: string | null;
  readonly runs?: readonly DraftPrWorkflowRunLike[] | null;
  readonly fetchError?: string | null;
}

export interface DraftPrBuildStatusResult {
  readonly state: DraftPrBuildState;
  readonly label: string;
  readonly detail: string;
  readonly runUrl?: string;
}

function cleanText(value: string | null | undefined): string | undefined {
  const clean = value?.trim();
  return clean || undefined;
}

function firstRun(runs: readonly DraftPrWorkflowRunLike[] | null | undefined): DraftPrWorkflowRunLike | undefined {
  return Array.isArray(runs) ? runs.find((run) => Boolean(run)) : undefined;
}

export function resolveDraftPrBuildStatus(input: DraftPrBuildStatusInput): DraftPrBuildStatusResult {
  const draftPrUrl = cleanText(input.draftPrUrl);
  if (!draftPrUrl) {
    return {
      state: 'unknown',
      label: 'Build unbekannt',
      detail: 'Kein Draft-PR-Link vorhanden; Buildstatus wird nicht abgefragt.',
    };
  }

  const fetchError = cleanText(input.fetchError);
  if (fetchError) {
    return {
      state: 'unknown',
      label: 'Build unbekannt',
      detail: `GitHub Buildstatus konnte nicht gelesen werden: ${fetchError}`,
    };
  }

  const run = firstRun(input.runs);
  if (!run) {
    return {
      state: 'unknown',
      label: 'Build unbekannt',
      detail: 'Keine GitHub Workflow-Runs sichtbar; kein grüner Status wird erfunden.',
    };
  }

  const status = cleanText(run.status)?.toLowerCase();
  const conclusion = cleanText(run.conclusion)?.toLowerCase();
  const runUrl = cleanText(run.html_url);

  if (status === 'queued' || status === 'requested' || status === 'waiting') {
    return {
      state: 'pending',
      label: 'Build wartet',
      detail: 'GitHub hat einen Run gemeldet, aber er läuft noch nicht.',
      runUrl,
    };
  }

  if (status && status !== 'completed') {
    return {
      state: 'running',
      label: 'Build läuft',
      detail: `GitHub Run Status: ${status}.`,
      runUrl,
    };
  }

  if (conclusion === 'success') {
    return {
      state: 'success',
      label: 'Build erfolgreich',
      detail: 'GitHub Run meldet success.',
      runUrl,
    };
  }

  if (conclusion === 'failure' || conclusion === 'cancelled' || conclusion === 'timed_out' || conclusion === 'action_required') {
    return {
      state: 'failure',
      label: 'Build fehlgeschlagen',
      detail: `GitHub Run Conclusion: ${conclusion}.`,
      runUrl,
    };
  }

  return {
    state: 'unknown',
    label: 'Build unbekannt',
    detail: 'GitHub Run ist vorhanden, aber ohne eindeutiges Ergebnis.',
    runUrl,
  };
}
