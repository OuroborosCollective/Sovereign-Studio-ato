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

  it('guards secret-shaped input before chat, typed interpretation, or repository execution', () => {
    const chat = source('src/features/release/PlayReleaseChat.tsx');
    const builder = source('src/features/product/containers/BuilderContainer.tsx');

    const submitStart = chat.indexOf('const submit = async');
    expect(submitStart).toBeGreaterThanOrEqual(0);
    const submitSource = chat.slice(submitStart, chat.indexOf('const runtimeColor', submitStart));

    const guardIndex = submitSource.indexOf('evaluateInputPolicy(text)');
    const plainChatIndex = submitSource.indexOf('await sendPlainChat(');
    const interpretationIndex = submitSource.indexOf('fetchSovereignDirectLlmInterpretation(');
    const executeIndex = submitSource.indexOf('await startCodingAction(action)');

    expect(guardIndex).toBeGreaterThanOrEqual(0);
    expect(plainChatIndex).toBeGreaterThan(guardIndex);
    expect(interpretationIndex).toBeGreaterThan(guardIndex);
    expect(executeIndex).toBeGreaterThan(guardIndex);
    expect(chat).toContain("if (inputPolicy.shouldBlock)");
    expect(chat).toContain('wurde nicht an das LLM gesendet');

    // The richer deferred builder remains separately claim-guarded even though
    // it is not mounted into the Play release root.
    expect(builder.match(/\bcheckChatClaim\(/g) ?? []).toHaveLength(1);
  });

  it('restores bounded repository coding without restoring monitor or auto-merge authority', () => {
    const chat = source('src/features/release/PlayReleaseChat.tsx');
    const agentRuntime = source('src/features/product/runtime/sovereignAgentRuntime.ts');

    expect(chat).toContain('SovereignAgentClient');
    expect(chat).toContain('fetchSovereignDirectLlmInterpretation');
    expect(chat).toContain('agentClient.startJob');
    expect(chat).toContain('agentClient.prepareDraftPr');
    expect(chat).toContain('agentClient.createDraftPr');
    expect(chat).toContain('Sovereign Aktivitätsverlauf');
    expect(chat).toContain('formatCuteThinkingLabel');
    expect(chat).not.toContain('mergePullRequest');
    expect(chat).not.toContain('mergeWhenGreen');

    expect(agentRuntime).toContain('draftPrOnly: true');
    expect(agentRuntime).toContain('allowAutoMerge: false');
    expect(agentRuntime).toContain('runtimeTruthRequired: true');
  });
});
