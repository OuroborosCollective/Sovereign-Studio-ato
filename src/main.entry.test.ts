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

  it('makes App.tsx the chat-only live surface', () => {
    const app = readSource('./App.tsx');

    expect(app).toContain('BuilderContainer');
    expect(app).toContain('data-testid="chat-only-app"');
    expect(app).toContain('data-layout="chat-only-live-entry"');
    expect(app).toContain('aria-label="Sovereign Chat"');
    expect(app).toContain('CHAT_ONLY_STYLE');
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
    expect(app).toContain('onStartAgent={startChatOnlyTask}');
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
