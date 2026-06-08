export type WorkflowCheck = 'idle' | 'running' | 'failed' | 'green';

export interface WorkflowAnalysis {
  check: WorkflowCheck;
  headline: string;
  userHint: string;
  nextAction: 'start' | 'wait' | 'fix' | 'confirm';
}

export function analyzeWorkflow(check: WorkflowCheck): WorkflowAnalysis {
  if (check === 'failed') {
    return {
      check,
      headline: 'Fehler gefunden',
      userHint: 'Ich springe zurueck in die Mitte und erstelle einen sichtbaren Fix.',
      nextAction: 'fix',
    };
  }
  if (check === 'green') {
    return {
      check,
      headline: 'Alles gruen',
      userHint: 'Die Pruefung ist sauber. Der naechste Schritt braucht deine Bestaetigung.',
      nextAction: 'confirm',
    };
  }
  if (check === 'running') {
    return {
      check,
      headline: 'Pruefung laeuft',
      userHint: 'Ich pruefe Struktur, Fehler und Workflows im Hintergrund.',
      nextAction: 'wait',
    };
  }
  return {
    check,
    headline: 'Bereit',
    userHint: 'Starte mit Idee oder Auftrag. Ich fuehre dich Schritt fuer Schritt.',
    nextAction: 'start',
  };
}
