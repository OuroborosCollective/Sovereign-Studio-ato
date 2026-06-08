import type { FlowStep } from './userFlow';

export const flowMessages: Record<FlowStep, string> = {
  idea: 'Beschreibe links deine Idee oder deinen Auftrag.',
  plan: 'Ich plane die Aenderung und bereite den Arbeitsbereich vor.',
  work: 'In der Mitte siehst du Chat, Datei-Editor und Live-Status.',
  check: 'Ich pruefe Struktur, Fehler und Workflows.',
  fix: 'Ich habe ein Problem gefunden und starte einen sichtbaren Fix.',
  ready: 'Alles sieht gut aus. Bitte bestaetige den naechsten Schritt.',
};

export function flowMessage(step: FlowStep): string {
  return flowMessages[step];
}
