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
    expect(wrapper).not.toContain('ProductMagicApp');
  });

  it('makes App.tsx the focused Play-release chat surface', () => {
    const app = readSource('./App.tsx');
    const chat = readSource('./features/release/PlayReleaseChat.tsx');

    expect(app).toContain("import { PlayReleaseChat } from './features/release/PlayReleaseChat'");
    expect(app).toContain('<PlayReleaseChat />');
    expect(app).not.toContain('BuilderContainer');
    expect(app).not.toContain('sovereign-monitor-app');
    expect(app).not.toContain('monitor-first-live-workspace');
    expect(chat).toContain('data-layout="play-release-chat"');
    expect(chat).toContain('aria-label="Sovereign Chat"');
  });

  it('keeps the deferred monitor implementation out of the current release root', () => {
    const app = readSource('./App.tsx');
    const builder = readSource('./features/product/containers/BuilderContainer.tsx');

    expect(builder).toContain('data-testid="sovereign-live-monitor-primary"');
    expect(builder).toContain('<MonitorCommunicationDock');
    expect(app).not.toContain('BuilderContainer');
    expect(app).not.toContain('getDesktopFrame');
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

  it('uses the current LLM route bridge instead of runtime auto-routing or visible app tabs', () => {
    const app = readSource('./App.tsx');
    const chat = readSource('./features/release/PlayReleaseChat.tsx');

    expect(app).not.toContain('decideSovereignAutoView');
    expect(app).not.toContain('setActiveTab(decision.tab)');
    expect(chat).toContain('fetchSovereignLlmRouteCatalog');
    expect(chat).toContain('fetchDevChatWorkerReply');
    expect(chat).toContain('DEV_CHAT_WORKER_DEFAULT_MODEL');
  });

  it('keeps repository memory and monitor wiring outside App while restoring bounded GitHub execution in Play chat', () => {
    const app = readSource('./App.tsx');
    const chat = readSource('./features/release/PlayReleaseChat.tsx');

    expect(app).not.toContain('searchReusableMemory');
    expect(app).not.toContain('startRepositoryExecution');
    expect(chat).not.toContain('searchReusableMemory');
    expect(chat).toContain('fetchSovereignDirectLlmInterpretation');
    expect(chat).toContain('startRepositoryExecution');
    expect(chat).toContain('prepareDraftPr');
    expect(chat).toContain('createDraftPr');
    expect(chat).toContain("interpretation.intent === 'draft_pr'");
    expect(chat).not.toContain('getDesktopFrame');
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
