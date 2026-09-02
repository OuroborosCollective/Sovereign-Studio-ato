import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8');
}

describe('main app entry', () => {
  it('renders the current Sovereign wrapper, not the legacy ProductMagic shell', () => {
    const main = readSource('./main.tsx');
    const wrapper = readSource('./SovereignAppWrapper.tsx');

    expect(main).toContain("import App from './SovereignAppWrapper'");
    expect(main).toContain('<App />');
    expect(wrapper).toContain("import App from './App'");
    expect(wrapper).toContain('<App />');
    expect(main).not.toContain("import ProductMagicApp from './ProductMagicApp'");
    expect(main).not.toContain('<ProductMagicApp />');
    expect(wrapper).not.toContain('ProductMagicApp');
  });

  it('makes App.tsx the chat-first live surface', () => {
    const app = readSource('./App.tsx');

    expect(app).toContain('BuilderContainer');
    expect(app).toContain('data-testid="sovereign-chat-app"');
    expect(app).toContain('data-layout="chat-first-agent-zero-background"');
    expect(app).toContain('aria-label="Sovereign Chat"');
    expect(app).toContain('CHAT_FIRST_STYLE');
    expect(app).not.toContain('data-layout="monitor-first-live-workspace"');
  });

  it('keeps the normal chat body and composer in the live builder', () => {
    const builder = readSource('./features/product/containers/BuilderContainer.tsx');

    expect(builder).toContain('data-testid="sovereign-chat-primary"');
    expect(builder).toContain('<MonitorCommunicationDock');
    expect(builder).toContain('mode="chat"');
    expect(builder).toContain('chat-primary-agent-zero-background');
    expect(builder).not.toContain('liveMonitorPrimary');
  });

  it('keeps the old dashboard shell out of the live app entry', () => {
    const app = readSource('./App.tsx');

    expect(app).not.toContain('SOVEREIGN_PRODUCT_TEMPLATE.tabs');
    expect(app).not.toContain('SOVEREIGN_PRODUCT_TEMPLATE.startTab');
    expect(app).not.toContain('tabbar__root');
    expect(app).not.toContain('automation__panel');
    expect(app).not.toContain('operator-monitor');
    expect(app).not.toContain('RepoSnapshotContainer');
    expect(app).not.toContain('RepoInsightPanelBridge');
  });

  it('keeps runtime auto-routing behind the chat instead of driving visible app tabs', () => {
    const app = readSource('./App.tsx');

    expect(app).not.toContain('decideSovereignAutoView');
    expect(app).not.toContain('setActiveTab(decision.tab)');
    expect(app).not.toContain('workflowStatus: workflowReport?.status');
    expect(app).toContain('onStartAgent={startMonitorTask}');
  });

  it('feeds canonical reusable memory into normal agent starts without making recall a start blocker', () => {
    const app = readSource('./App.tsx');

    expect(app).toContain('searchReusableMemory(query, 6)');
    expect(app).toContain('reusableMemoryContext(memory)');
    expect(app).toContain('evidenceText = await evidenceWithReusableMemory(nextMission)');
    expect(app).toContain('return query;');
  });

  it('keeps the release shell styling contract in the Android web build', () => {
    const css = readSource('./index.css');

    expect(css).toContain('--surface-1');
    expect(css).toContain('--accent-2');
    expect(css).toContain('Release shell');
    expect(css).toContain('Container runtime');
    expect(css).toContain('Android phones, foldables and tablets only');
  });
});
