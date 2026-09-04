import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '..');

function source(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

describe('Sovereign chat-first primary-surface contract', () => {
  it('mounts the authenticated chat workspace while preserving the observatory route', () => {
    const app = source('src/App.tsx');

    expect(app).toContain('BuilderContainer');
    expect(app).toContain('data-testid="sovereign-chat-app"');
    expect(app).toContain('data-layout="chat-first-agent-zero-background"');
    expect(app).toContain('aria-label="Sovereign Workspace Monitor"');
    expect(app).toContain('<BuilderContainer');
    expect(app).toContain('onStartAgent={startMonitorTask}');
    expect(app).not.toContain('PlayReleaseChat');
    expect(app).not.toContain('data-layout="monitor-first-live-workspace"');

    expect(app).toContain('EvidenceObservatoryAtlas');
    expect(app).toContain("window.location.pathname === '/observatory'");
    expect(app).toContain("window.location.pathname === '/evidence-observatory'");
    expect(app).toContain("new URLSearchParams(window.location.search).get('observatory') === '1'");
  });

  it('keeps chat primary while monitor diagnostics, model picker and menu remain reachable', () => {
    const builder = source('src/features/product/containers/BuilderContainer.tsx');
    const monitor = source('src/features/product/components/LiveWorkspaceMonitor.tsx');
    const dock = source('src/features/product/components/MonitorCommunicationDock.tsx');

    expect(builder).toContain('MonitorCommunicationDock');
    expect(builder).toContain('chat-primary-agent-zero-background');
    expect(builder).toContain('aria-label="Menü"');
    expect(builder).toContain('aria-label="Sovereign Seitenmenü"');
    expect(monitor).toContain('live-workspace-monitor-desktop');
    expect(dock).toContain('data-testid="monitor-communication-dock"');
    expect(dock).toContain('data-testid="sovereign-llm-route-picker-trigger"');
    expect(dock).toContain('aria-label="Modelle durchsuchen"');
  });

  it('guards chat input before the LLM compiler and keeps execution behind the visible draft confirmation', () => {
    const builder = source('src/features/product/containers/BuilderContainer.tsx');

    const guardIndex = builder.indexOf('evaluateInputPolicy(submittedText)');
    const requestIndex = builder.indexOf('fetchSovereignDirectLlmInterpretation({');
    expect(guardIndex).toBeGreaterThanOrEqual(0);
    expect(requestIndex).toBeGreaterThan(guardIndex);
    expect(builder).toContain('createStructuredIntegrationIntentDraft');
    expect(builder).toContain('startAgentFromApprovedDraft');
    expect(builder).toContain('onConfirm={() => {');
    expect(builder).toContain('Nur der Zugang wird geprüft; der Repository-Auftrag bleibt unbestätigt.');
    expect(builder.match(/\bcheckChatClaim\(/g) ?? []).toHaveLength(1);
  });
});
