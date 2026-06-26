import type { OpenHandsEnterpriseConfig } from './openhandsEnterpriseRuntime';

/** Status level for briefing items */
export type BriefingStatus = 'ok' | 'warning' | 'blocked' | 'info';

/** A single briefing item shown to the operator */
export interface BriefingItem {
  readonly id: string;
  readonly label: string;
  readonly value: string;
  readonly status: BriefingStatus;
  readonly hint?: string;
}

/** Section grouping related briefing items */
export interface BriefingSection {
  readonly id: string;
  readonly title: string;
  readonly items: readonly BriefingItem[];
}

/** Complete operator briefing for OpenHands */
export interface OpenHandsOperatorBriefing {
  readonly sections: readonly BriefingSection[];
  readonly blockedCount: number;
  readonly warningCount: number;
  readonly isBlocked: boolean;
}

/** Trigger markers for starting OpenHands */
export interface OpenHandsTriggerInfo {
  readonly labels: readonly string[];
  readonly commentMarker: string;
  readonly webhookSupported: boolean;
}

/** Secrets and settings that might be missing */
export interface OpenHandsSecretsStatus {
  readonly agentApiUrl: boolean;
  readonly adminConsoleUrl: boolean;
  readonly httpsRequired: boolean;
}

/** Output type information */
export interface OpenHandsOutputType {
  readonly draftPr: boolean;
  readonly branch: boolean;
  readonly logOnly: boolean;
}

/** Build the trigger info section */
function buildTriggerSection(): BriefingSection {
  return {
    id: 'triggers',
    title: 'OpenHands starten',
    items: [
      {
        id: 'labels',
        label: 'Start-Labels',
        value: 'openhands-review, openhands-fix, openhands-agent',
        status: 'info',
        hint: 'Ein Label auf ein Issue oder PR setzen startet einen neuen OpenHands-Lauf.',
      },
      {
        id: 'comment-marker',
        label: 'Kommentar-Marker',
        value: '/openhands',
        status: 'info',
        hint: 'Ein Kommentar mit "/openhands" in einem Issue oder PR startet ebenfalls einen Lauf.',
      },
      {
        id: 'webhook',
        label: 'Webhook-Unterstützung',
        value: 'Ja',
        status: 'ok',
        hint: 'OpenHands kann auch per Webhook-Events getriggert werden.',
      },
    ],
  };
}

/** Build the workflow info section */
function buildWorkflowSection(): BriefingSection {
  return {
    id: 'workflows',
    title: 'Aktive Workflows',
    items: [
      {
        id: 'draft-pr-workflow',
        label: 'Draft PR Workflow',
        value: 'Aktiv',
        status: 'ok',
        hint: 'Erstellt einen Branch und Draft PR nach erfolgreichem Lauf.',
      },
      {
        id: 'test-workflow',
        label: 'Test Workflow',
        value: 'Aktiv',
        status: 'ok',
        hint: 'Führt Tests aus und meldet Ergebnisse.',
      },
      {
        id: 'lint-workflow',
        label: 'Lint Workflow',
        value: 'Aktiv',
        status: 'ok',
        hint: 'Prüft Code-Qualität und Formatierung.',
      },
    ],
  };
}

/** Build the output type section */
function buildOutputSection(): BriefingSection {
  return {
    id: 'output',
    title: 'Lauf-Ergebnis',
    items: [
      {
        id: 'draft-pr',
        label: 'Draft PR',
        value: 'Ja',
        status: 'ok',
        hint: 'Ergebnis ist immer ein Draft PR, kein direkter Merge.',
      },
      {
        id: 'branch',
        label: 'Branch',
        value: 'Ja',
        status: 'ok',
        hint: 'Jeder Lauf erstellt einen separaten Branch mit Änderungen.',
      },
      {
        id: 'log',
        label: 'Logs',
        value: 'Ja',
        status: 'info',
        hint: 'Alle Schritte werden geloggt. Logs sind im Admin Console einsehbar.',
      },
    ],
  };
}

/** Build the configuration section based on current config */
function buildConfigSection(config: OpenHandsEnterpriseConfig): BriefingSection {
  const items: BriefingItem[] = [];

  // Agent API URL
  if (!config.agentApiUrl) {
    items.push({
      id: 'agent-api-url',
      label: 'Agent API URL',
      value: 'Fehlt',
      status: 'blocked',
      hint: 'Setze VITE_OPENHANDS_AGENT_API_URL in der .env Datei.',
    });
  } else {
    items.push({
      id: 'agent-api-url',
      label: 'Agent API URL',
      value: config.agentApiUrl,
      status: 'ok',
    });
  }

  // Admin Console URL
  if (!config.adminConsoleUrl) {
    items.push({
      id: 'admin-console-url',
      label: 'Admin Console URL',
      value: 'Fehlt',
      status: 'warning',
      hint: 'Optional: Setze VITE_OPENHANDS_ADMIN_CONSOLE_URL für Admin-Zugang.',
    });
  } else {
    items.push({
      id: 'admin-console-url',
      label: 'Admin Console URL',
      value: config.adminConsoleUrl,
      status: 'ok',
    });
  }

  // HTTPS check
  const isHttps = config.agentApiUrl?.startsWith('https://') ?? false;
  const isLocalhost = config.agentApiUrl?.includes('localhost') ?? false;
  if (config.agentApiUrl && !isHttps && !isLocalhost) {
    items.push({
      id: 'https-required',
      label: 'Sicherheit',
      value: 'HTTP (unsicher)',
      status: 'blocked',
      hint: 'Außer für localhost muss HTTPS verwendet werden.',
    });
  } else if (config.agentApiUrl) {
    items.push({
      id: 'https-required',
      label: 'Sicherheit',
      value: isLocalhost ? 'localhost (erlaubt)' : 'HTTPS',
      status: 'ok',
    });
  }

  // Enabled status
  items.push({
    id: 'enabled',
    label: 'OpenHands aktiviert',
    value: config.enabled ? 'Ja' : 'Nein',
    status: config.enabled ? 'ok' : 'warning',
    hint: config.enabled ? 'OpenHands Enterprise Runtime ist aktiv.' : 'Setze VITE_OPENHANDS_ENABLED=true um OpenHands zu aktivieren.',
  });

  // Ready status
  items.push({
    id: 'ready',
    label: 'Konfiguration bereit',
    value: config.ready ? 'Ja' : 'Nein',
    status: config.ready ? 'ok' : 'blocked',
    hint: config.ready ? 'Alle erforderlichen Einstellungen sind vorhanden.' : config.reason,
  });

  return {
    id: 'configuration',
    title: 'Konfiguration prüfen',
    items,
  };
}

/** Build the secrets/settings missing section */
function buildSecretsSection(config: OpenHandsEnterpriseConfig): BriefingSection {
  const secrets: OpenHandsSecretsStatus = {
    agentApiUrl: Boolean(config.agentApiUrl),
    adminConsoleUrl: Boolean(config.adminConsoleUrl),
    httpsRequired: config.agentApiUrl?.startsWith('https://') ?? false,
  };

  const items: BriefingItem[] = [];

  if (!secrets.agentApiUrl) {
    items.push({
      id: 'missing-agent-api',
      label: 'Agent API URL fehlt',
      value: 'Erforderlich',
      status: 'blocked',
      hint: 'VITE_OPENHANDS_AGENT_API_URL muss gesetzt sein.',
    });
  }

  if (!secrets.adminConsoleUrl) {
    items.push({
      id: 'missing-admin-console',
      label: 'Admin Console URL fehlt',
      value: 'Optional',
      status: 'warning',
      hint: 'VITE_OPENHANDS_ADMIN_CONSOLE_URL ist optional aber empfohlen.',
    });
  }

  // Check if https is missing for non-localhost
  const isHttps = config.agentApiUrl?.startsWith('https://') ?? false;
  const isLocalhost = config.agentApiUrl?.includes('localhost') ?? false;
  if (config.agentApiUrl && !isHttps && !isLocalhost) {
    items.push({
      id: 'missing-https',
      label: 'HTTPS fehlt',
      value: 'Blockiert',
      status: 'blocked',
      hint: 'Nur HTTPS ist außerhalb von localhost erlaubt.',
    });
  }

  if (items.length === 0) {
    items.push({
      id: 'all-configured',
      label: 'Alle Einstellungen',
      value: 'OK',
      status: 'ok',
      hint: 'Alle erforderlichen Secrets und Einstellungen sind konfiguriert.',
    });
  }

  return {
    id: 'secrets',
    title: 'Fehlende Secrets/Settings',
    items,
  };
}

/** Build complete operator briefing from OpenHands config */
export function buildOpenHandsOperatorBriefing(
  config: OpenHandsEnterpriseConfig
): OpenHandsOperatorBriefing {
  const sections: BriefingSection[] = [
    buildTriggerSection(),
    buildWorkflowSection(),
    buildOutputSection(),
    buildConfigSection(config),
    buildSecretsSection(config),
  ];

  let blockedCount = 0;
  let warningCount = 0;

  for (const section of sections) {
    for (const item of section.items) {
      if (item.status === 'blocked') blockedCount++;
      else if (item.status === 'warning') warningCount++;
    }
  }

  return {
    sections,
    blockedCount,
    warningCount,
    isBlocked: blockedCount > 0,
  };
}

/** Get a summary string for the briefing */
export function summarizeOpenHandsBriefing(briefing: OpenHandsOperatorBriefing): string {
  if (briefing.isBlocked) {
    return `${briefing.blockedCount} blockierende Problem(e) blockieren den OpenHands-Lauf.`;
  }
  if (briefing.warningCount > 0) {
    return `${briefing.warningCount} Warnung(en) vorhanden. OpenHands kann starten, aber prüfe die Einstellungen.`;
  }
  return 'OpenHands ist vollständig konfiguriert und bereit zum Starten.';
}

/** Status color mapping for UI */
export const BRIEFING_STATUS_COLORS: Record<BriefingStatus, string> = {
  ok: '#34d399',      // green
  warning: '#fbbf24', // amber
  blocked: '#fb7185', // red
  info: '#22d3ee',    // cyan
};

/** Status label mapping for UI */
export const BRIEFING_STATUS_LABELS: Record<BriefingStatus, string> = {
  ok: 'OK',
  warning: 'Warnung',
  blocked: 'Blockiert',
  info: 'Info',
};