import { resolveSovereignAgentConfig, type SovereignAgentConfig } from './sovereignAgentRuntime';
import type { EvidenceCategory, EvidenceStatus } from './evidenceLedger';

export type BriefingStatus = 'ok' | 'warning' | 'blocked' | 'info';

export interface BriefingSection {
  id: string;
  title: string;
  status: BriefingStatus;
  items: readonly BriefingItem[];
  isExpanded?: boolean;
}

export interface BriefingItem {
  label: string;
  value: string;
  status?: BriefingStatus;
}

export interface OpenHandsOperatorBriefing {
  sections: readonly BriefingSection[];
  blockedCount: number;
  warningCount: number;
  isBlocked: boolean;
}

function getTriggerLabels(): BriefingItem[] {
  return [
    { label: 'Labels', value: 'openhands-review, openhands-fix, openhands-agent', status: 'info' },
    { label: 'Kommentar', value: '/openhands in Issue/PR Kommentar', status: 'info' },
    { label: 'Webhook', value: 'OpenHands Webhook Events', status: 'info' },
  ];
}

function getActiveWorkflows(): BriefingItem[] {
  return [
    { label: 'Draft PR Workflow', value: 'Erstellt Branch + Draft PR nach erfolgreichem Lauf', status: 'ok' },
    { label: 'Test Workflow', value: 'Führt Tests aus und meldet Ergebnisse', status: 'ok' },
    { label: 'Lint Workflow', value: 'Prüft Code-Qualität und Formatierung', status: 'ok' },
  ];
}

function getRunResult(): BriefingItem[] {
  return [
    { label: 'Draft PR', value: 'Immer ein Draft PR, kein direkter Merge', status: 'ok' },
    { label: 'Branch', value: 'Jeder Lauf erstellt einen separaten Branch', status: 'ok' },
    { label: 'Logs', value: 'Alle Schritte werden geloggt (Admin Console)', status: 'ok' },
  ];
}

function getConfigurationSection(config: SovereignAgentConfig): BriefingSection {
  const items: BriefingItem[] = [];
  let status: BriefingStatus = 'ok';

  // Agent API URL check
  if (!config.agentApiUrl) {
    items.push({ label: 'Agent API URL', value: 'Nicht konfiguriert', status: 'blocked' });
    status = 'blocked';
  } else if (!config.ready) {
    items.push({ label: 'Agent API URL', value: config.reason, status: 'blocked' });
    status = 'blocked';
  } else {
    items.push({ label: 'Agent API URL', value: config.agentApiUrl, status: 'ok' });
  }

  // Deployment mode
  items.push({
    label: 'Deployment Mode',
    value: config.deploymentMode === 'disabled' ? 'Deaktiviert' : config.deploymentMode,
    status: config.deploymentMode === 'disabled' ? 'warning' : 'ok',
  });

  // Ready status
  items.push({
    label: 'Status',
    value: config.ready ? 'Bereit' : 'Nicht bereit',
    status: config.ready ? 'ok' : 'blocked',
  });

  return {
    id: 'configuration',
    title: 'Konfiguration prüfen',
    status,
    items,
  };
}

function getMissingSecretsSection(config: SovereignAgentConfig): BriefingSection {
  const items: BriefingItem[] = [];
  let status: BriefingStatus = 'ok';

  // Missing Agent API URL
  if (!config.agentApiUrl) {
    items.push({ label: 'Agent API URL', value: 'Erforderlich → Blockiert', status: 'blocked' });
    status = 'blocked';
  } else if (!config.ready) {
    items.push({ label: 'Konfiguration', value: config.reason, status: 'blocked' });
    status = 'blocked';
  } else {
    items.push({ label: 'Alle erforderlichen Settings', value: 'Vorhanden', status: 'ok' });
  }

  return {
    id: 'missing-secrets',
    title: 'Fehlende Secrets/Settings',
    status,
    items,
  };
}

export function buildOpenHandsOperatorBriefing(): OpenHandsOperatorBriefing {
  const config = resolveSovereignAgentConfig();

  const sections: BriefingSection[] = [
    {
      id: 'triggers',
      title: 'OpenHands starten',
      status: 'info',
      items: getTriggerLabels(),
    },
    {
      id: 'workflows',
      title: 'Aktive Workflows',
      status: 'ok',
      items: getActiveWorkflows(),
    },
    {
      id: 'run-result',
      title: 'Lauf-Ergebnis',
      status: 'ok',
      items: getRunResult(),
    },
    getConfigurationSection(config),
    getMissingSecretsSection(config),
  ];

  const blockedCount = sections.filter((s) => s.status === 'blocked').length;
  const warningCount = sections.filter((s) => s.status === 'warning').length;

  return {
    sections,
    blockedCount,
    warningCount,
    isBlocked: blockedCount > 0,
  };
}
