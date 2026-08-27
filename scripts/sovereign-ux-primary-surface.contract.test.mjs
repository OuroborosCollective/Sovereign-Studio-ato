import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '..');

function source(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

describe('Sovereign Play-release primary-surface contract', () => {
  it('mounts the focused authenticated chat while keeping the unfinished monitor out of the release root', () => {
    const app = source('src/App.tsx');
    const chat = source('src/features/release/PlayReleaseChat.tsx');

    expect(app).toContain("import { PlayReleaseChat } from './features/release/PlayReleaseChat'");
    expect(app).toContain('<PlayReleaseChat />');
    expect(app).not.toContain('sovereign-monitor-app');
    expect(app).not.toContain('LiveWorkspaceMonitor');
    expect(app).not.toContain('BuilderContainer');

    expect(chat).toContain('data-testid="sovereign-release-chat"');
    expect(chat).toContain('data-layout="play-release-chat"');
    expect(chat).toContain('fetchSovereignLlmRouteCatalog');
    expect(chat).toContain('fetchDevChatWorkerReply');
    expect(chat).toContain('DEV_CHAT_WORKER_DEFAULT_MODEL');
    expect(chat).toContain('data-testid="play-release-menu-frame"');
    expect(chat).toContain("['chat', '💬', 'Chat']");
    expect(chat).toContain("['github', '⌘', 'GitHub']");
    expect(chat).toContain("['models', '◫', 'Modelle']");
    expect(chat).toContain("['account', '◉', 'Konto']");
    expect(chat).toContain('aria-label="LLM Route"');
    expect(chat).toContain('deriveReleaseGuideState');
    expect(chat).not.toContain('getDesktopFrame');
    expect(chat).not.toContain('VncScreen');
  });

  it('keeps the deferred monitor implementation in the repository without mounting it into the Play root', () => {
    const app = source('src/App.tsx');
    const builder = source('src/features/product/containers/BuilderContainer.tsx');
    const monitor = source('src/features/product/components/LiveWorkspaceMonitor.tsx');

    expect(builder).toContain('MonitorCommunicationDock');
    expect(builder).toContain('live-desktop-monitor-primary');
    expect(monitor).toContain('live-workspace-monitor-desktop');
    expect(app).not.toContain('BuilderContainer');
  });

  it('guards release-chat secret input before the LLM bridge and preserves the existing deferred claim guard', () => {
    const chat = source('src/features/release/PlayReleaseChat.tsx');
    const builder = source('src/features/product/containers/BuilderContainer.tsx');

    const guardIndex = chat.indexOf('evaluateInputPolicy(text)');
    const requestIndex = chat.indexOf('fetchDevChatWorkerReply(');
    expect(guardIndex).toBeGreaterThanOrEqual(0);
    expect(requestIndex).toBeGreaterThan(guardIndex);
    expect(builder.match(/\bcheckChatClaim\(/g) ?? []).toHaveLength(1);
  });
});
