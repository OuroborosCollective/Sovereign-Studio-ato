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

  it('makes the Play Release chat the current-session primary surface', () => {
    const app = readSource('./App.tsx');

    expect(app).toContain('PlayReleaseChat');
    expect(app).toContain('data-testid="sovereign-chat-app"');
    expect(app).toContain('data-layout="chat-first-agent-zero-background"');
    expect(app).toContain('data-primary-surface="play-release-chat"');
    expect(app).toContain('data-truth-scope="current-chat-session-only"');
    expect(app).toContain('aria-label="Sovereign Chat"');
    expect(app).toContain('CHAT_FIRST_STYLE');
    expect(app).not.toContain('BuilderContainer');
    expect(app).not.toContain('RESTORE_LATEST_JOB');
  });

  it('keeps repository execution and Draft-PR publication on the visible release-chat path', () => {
    const release = readSource('./features/release/PlayReleaseChat.tsx');

    expect(release).toContain('startRepositoryExecution');
    expect(release).toContain('prepareDraftPr');
    expect(release).toContain('createDraftPr');
    expect(release).toContain('Draft PR erstellen');
    expect(release).toContain('readbackHeadSha');
    expect(release).toContain('GitHub-Änderungsentwurf erkannt');
    expect(release).not.toContain('listJobs(');
  });

  it('preserves the evidence observatory as an explicit route instead of mixing it into live runtime truth', () => {
    const app = readSource('./App.tsx');

    expect(app).toContain('EvidenceObservatoryAtlas');
    expect(app).toContain("window.location.pathname === '/observatory'");
    expect(app).toContain("window.location.pathname === '/evidence-observatory'");
    expect(app).toContain("new URLSearchParams(window.location.search).get('observatory') === '1'");
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

  it('keeps the release shell styling contract in the Android web build', () => {
    const css = readSource('./index.css');

    expect(css).toContain('--surface-1');
    expect(css).toContain('--accent-2');
    expect(css).toContain('Release shell');
    expect(css).toContain('Container runtime');
    expect(css).toContain('Android phones, foldables and tablets only');
  });
});
