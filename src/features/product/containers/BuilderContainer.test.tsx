import React from "react";
import { Provider } from "react-redux";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BuilderContainer } from "./BuilderContainer";
import * as areInferenceApi from "../../inference/areInferenceApi";
import type { AreInferenceResult } from "../../inference/areInferenceApi";
import { useToolchainStore } from "../../toolchain/useToolchainStore";
import { useUserStore } from "../../user/useUserStore";
import { useSovereignToolInspectionStore } from "../runtime/sovereignToolInspectionRuntime";
import type {
  SovereignLiveProjection,
  SovereignLiveProjectionState,
  SovereignWorkspaceEvidenceAnchor,
} from "../runtime/sovereignAgentRuntime";
import { store } from "../../../store";

// Mock useBilling to avoid Redux context errors from PaywallModal
vi.mock("../../../features/billing/hooks/useBilling", () => ({
  useBilling: () => ({
    credits: 100,
    packages: [],
    isLoading: false,
    error: null,
    canUseCredits: true,
    purchaseCredits: vi.fn(),
  }),
}));

function renderWithProviders(ui: React.ReactElement) {
  return render(<Provider store={store}>{ui}</Provider>);
}

function baseProps() {
  return {
    mission: "Bitte mobile UX verbessern und Log direkt sichtbar machen.",
    repoReady: true,
    repoReason: "Repo ready.",
    repoBusy: false,
    runtimeBusy: false,
    isPublishing: false,
    sovereignSummary: "Package summary",
    sovereignPreview: '{ "ok": true }',
    onMissionChange: vi.fn(),
    onGenerateIdeas: vi.fn(),
    onGenerateErrorWorkflow: vi.fn(),
    onPublishDraftPr: vi.fn(),
  };
}

function chatField(): HTMLTextAreaElement {
  return screen.getByLabelText('Codeauftrag an Sovereign') as HTMLTextAreaElement;
}

function sendButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Senden" }) as HTMLButtonElement;
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function isRoutePickerBootstrap(input: RequestInfo | URL): boolean {
  const url = new URL(requestUrl(input), 'https://sovereign.test');
  return url.pathname.endsWith('/api/llm/routes') && url.searchParams.get('purpose') === 'picker';
}

function isAuthBootstrapRequest(input: RequestInfo | URL): boolean {
  return requestUrl(input).includes("/api/auth/me");
}

function isToolchainBootstrapRequest(input: RequestInfo | URL): boolean {
  const url = requestUrl(input);
  return url.includes('/api/toolchain/user-tools')
    || url.includes('/api/toolchain/universal/manifest')
    || url.includes('/api/toolchain/skills/list');
}

function isGitHubApiRequest(input: RequestInfo | URL): boolean {
  return requestUrl(input).startsWith('https://api.github.com/');
}

const TEST_AUTH_USER = {
  id: 'runtime-health-user',
  email: 'runtime-health@example.com',
  displayName: 'Runtime Health',
  role: 'user' as const,
  credits: 100,
  subscriptionStatus: 'free' as const,
  isBanned: false,
  createdAt: 1,
};

function authBootstrapResponse(): Response {
  return jsonResponse(TEST_AUTH_USER);
}

const TEST_LITELLM_MODEL = 'deepseek-r1';

function liteLlmRouteCatalogResponse(): Response {
  return jsonResponse({
    routes: [{
      id: 'test-chat-route',
      defaultModelId: TEST_LITELLM_MODEL,
      enabled: true,
      provider: 'freellm',
      billingCategory: 'free',
      fundingMode: 'provider_free_quota',
      capabilities: { codeActionContract: true },
    }],
  });
}

function lastUserTextFromLiteLlmRequest(init?: RequestInit): string {
  if (typeof init?.body !== 'string') return '';
  try {
    const payload = JSON.parse(init.body) as {
      readonly messages?: readonly { readonly role?: unknown; readonly content?: unknown }[];
    };
    const message = [...(payload.messages ?? [])].reverse().find((entry) => entry.role === 'user');
    return typeof message?.content === 'string' ? message.content : '';
  } catch {
    return '';
  }
}

function testIntentEnvelope(text: string, _legacyAssistantText = '') {
  const lower = text.toLocaleLowerCase('de-DE');
  const draftPr = /draft\s*pr|pull\s*request/.test(lower) && /mach|erstell|implement|reparier|fix|bring/.test(lower);
  const write = draftPr || /implement|reparier|fix|änder|aktualisier|verbesser|bau\b|erzeug|prüfe|teste/.test(lower);
  return {
    mode: write ? 'action' : 'clarify',
    intent: draftPr ? 'draft_pr' : write ? 'code_execution' : 'unknown',
    action_disposition: 'review',
    clarification_code: write ? 'none' : 'change_required',
    is_startup: false,
    confidence: 0.96,
    language: 'de',
  };
}

async function normalizeLiteLlmMockResponse(
  response: Response,
  userText: string,
): Promise<Response> {
  if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
    return response;
  }
  const payload = await response.clone().json() as {
    readonly choices?: readonly { readonly message?: { readonly content?: unknown } }[];
    readonly model?: unknown;
  };
  const content = payload.choices?.[0]?.message?.content;
  if (typeof content !== 'string') return response;
  try {
    const parsed = JSON.parse(content) as { readonly mode?: unknown };
    if (parsed.mode === 'clarify' || parsed.mode === 'action') return response;
  } catch {
    // Legacy test replies are wrapped below into the strict Sovereign LLM intent envelope.
  }
  return jsonResponse({
    ...payload,
    model: typeof payload.model === 'string' ? payload.model : TEST_LITELLM_MODEL,
    choices: [{ message: { content: JSON.stringify(testIntentEnvelope(userText, content)) } }],
  });
}

function mockFetchSequence(...responses: Array<Response | (() => Response | Promise<Response>)>) {
  const queue = [...responses];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (isAuthBootstrapRequest(input)) return authBootstrapResponse();
    const url = requestUrl(input);
    if (isToolchainBootstrapRequest(input)) {
      return runtimeSupportResponse(url, init) ?? jsonResponse({ ok: true });
    }
    if (url.includes('/api/llm/routes')) return liteLlmRouteCatalogResponse();
    if (url.includes('/api/user/agent/github-access/validate')) {
      const first = queue[0];
      const second = queue[1];
      if (first instanceof Response) {
        const explicitValidation = await first.clone().json().catch(() => null) as Record<string, unknown> | null;
        if (explicitValidation && ('canWrite' in explicitValidation || 'code' in explicitValidation)) {
          queue.shift();
          return first;
        }
      }
      if (first instanceof Response && second instanceof Response) {
        const firstPayload = await first.clone().json().catch(() => null) as Record<string, unknown> | null;
        const secondPayload = await second.clone().json().catch(() => null) as { permissions?: { push?: boolean } } | null;
        if (firstPayload && 'login' in firstPayload && secondPayload?.permissions) {
          queue.splice(0, 2);
          const canWrite = secondPayload.permissions.push === true;
          return jsonResponse({
            ok: canWrite,
            canWrite,
            code: canWrite ? 'ready' : 'write_permission_missing',
            error: canWrite ? null : 'GitHub-Zugang hat keinen Schreibzugriff.',
          });
        }
      }
      return jsonResponse({ ok: true, canWrite: true, code: 'ready', error: null });
    }
    if (url.includes('/api/llm/chat')) {
      const next = queue.shift();
      const userText = lastUserTextFromLiteLlmRequest(init);
      const response = next
        ? typeof next === 'function' ? await next() : next
        : jsonResponse({ choices: [{ message: { content: 'Worker Antwort aus Cloudflare Route.' } }] });
      return normalizeLiteLlmMockResponse(response, userText);
    }
    if (isGitHubApiRequest(input)) {
      if (url.includes('/commits/')) return jsonResponse({ sha: 'c'.repeat(40) });
      const next = queue.shift();
      if (!next) return jsonResponse({ message: 'Unexpected GitHub API request in test.' }, 500);
      return typeof next === 'function' ? next() : next;
    }
    return runtimeSupportResponse(url, init) ?? jsonResponse({ ok: true });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function nonAuthFetchCalls(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.filter(([input]) => {
    const request = input as RequestInfo | URL;
    const url = requestUrl(request);
    if (isRoutePickerBootstrap(request)) return false;
    return (isGitHubApiRequest(request) && !url.includes('/commits/'))
      || url.includes('/api/llm/routes')
      || url.includes('/api/llm/chat');
  });
}

function mockWorkerReply(text = "Worker Antwort aus Cloudflare Route.") {
  mockFetchSequence(jsonResponse({ choices: [{ message: { content: text } }] }));
}

function fakeGitHubPat(): string {
  return [
    ['g', 'hp'].join(''),
    '_',
    'ABCDEFGH',
    'IJKLMNOP',
    'QRSTUVWX',
    'YZabcdef',
    '0123456789',
  ].join('');
}

const TEST_CHAT_SESSION_ID = 'livechat-0123456789abcdef01234567';
let testChatBubbleSequence = 0;
let testChatSession = {
  schemaVersion: 'sovereign.live-workspace-chat-session.v1',
  persistence: 'postgresql',
  sessionId: TEST_CHAT_SESSION_ID,
  repositoryIdentity: 'UNBOUND',
  repositoryBranch: 'main',
  recordedAt: '2026-08-23T00:00:00.000Z',
};

function requestJsonBody(init?: RequestInit): Record<string, unknown> {
  if (typeof init?.body !== 'string') return {};
  try {
    const payload = JSON.parse(init.body) as unknown;
    return payload && typeof payload === 'object' && !Array.isArray(payload)
      ? payload as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

function testMissionBubble(init?: RequestInit) {
  const body = requestJsonBody(init);
  testChatBubbleSequence += 1;
  return {
    schemaVersion: 'sovereign.live-workspace-chat-bubble.v1',
    sessionId: TEST_CHAT_SESSION_ID,
    clientMessageId: typeof body.clientMessageId === 'string'
      ? body.clientMessageId
      : `mission-test-${testChatBubbleSequence}`,
    bubbleKind: 'MISSION_INPUT',
    sourceKind: 'USER_INPUT',
    text: typeof body.text === 'string' ? body.text : 'Test mission',
    canonicalReferenceHashes: [],
    workflowState: 'RECORDED',
    bubbleHash: testChatBubbleSequence.toString(16).padStart(64, '0'),
    recordedAt: '2026-08-23T00:00:00.000Z',
    authoritative: false,
  };
}

function runtimeSupportResponse(url: string, init?: RequestInit): Response | null {
  if (url.includes('/api/user/agent/live-workspace/chat-session')) {
    const method = (init?.method ?? 'GET').toUpperCase();
    if (url.endsWith('/chat-session') && method === 'POST') {
      const body = requestJsonBody(init);
      testChatSession = {
        ...testChatSession,
        repositoryIdentity: typeof body.repositoryIdentity === 'string'
          ? body.repositoryIdentity
          : 'UNBOUND',
        repositoryBranch: typeof body.repositoryBranch === 'string'
          ? body.repositoryBranch
          : 'main',
      };
      return jsonResponse({ session: testChatSession });
    }
    if (url.endsWith('/bubbles') && method === 'GET') {
      return jsonResponse({ session: testChatSession, bubbles: [] });
    }
    if (url.endsWith('/mission') && method === 'POST') {
      return jsonResponse({ bubble: testMissionBubble(init) }, 201);
    }
  }
  if (url.includes('/api/llm/routes')) return liteLlmRouteCatalogResponse();
  if (url.includes('/api/user/agent/github-access/scope')) {
    return jsonResponse({ ok: true, scope: 'v1.test-scope.signature' });
  }
  if (url.includes('/api/user/agent/github-access/validate')) {
    return jsonResponse({ ok: true, canWrite: true, code: 'ready', error: null });
  }
  if (url.includes('/api/llm/chat')) {
    const userText = lastUserTextFromLiteLlmRequest(init);
    return jsonResponse({
      model: TEST_LITELLM_MODEL,
      choices: [{ message: { content: JSON.stringify(testIntentEnvelope(
        userText,
        'Worker response must remain pending.',
      )) } }],
    });
  }
  if (url.includes('/api/toolchain/user-tools')) {
    return jsonResponse({ tools: [], allowed_repos: [], rules: {} });
  }
  if (url.includes('/api/toolchain/universal/manifest')) {
    return jsonResponse({
      name: 'test-universal-toolchain',
      version: 'test',
      runtime: 'embedded',
      tools: [],
      policy: {
        autoLoad: true,
        pushToMain: false,
        draftPrOnly: true,
        confirmRequired: true,
        arbitraryShell: false,
        directProductionRunner: false,
        directGithubToken: false,
        auditEvidence: true,
      },
    });
  }
  if (url.includes('/api/toolchain/skills/list')) return jsonResponse({ skills: [] });
  return null;
}

function localAreInferenceResult(onlineAvailable = true): AreInferenceResult {
  return {
    ok: true,
    schemaVersion: 1,
    stateHash: 'a'.repeat(64),
    state: {
      schemaVersion: 1,
      promptSha256: 'b'.repeat(64),
      repository: {
        owner: 'OuroborosCollective',
        repo: 'Sovereign-Studio-ato',
        branch: 'main',
        repositoryRevision: 'c'.repeat(40),
        files: [],
        evidenceComplete: true,
      },
      knowledgeRevision: 'd'.repeat(64),
      experienceRevision: 'e'.repeat(64),
      embeddingModelHash: 'f'.repeat(64),
      activeCapabilities: [],
      onlineAvailable,
    },
    decision: 'local',
    adapter: 'test-local',
    confidence: 1,
    knowledgeConfidence: 0,
    experienceConfidence: 0,
    selectedKnowledgeIds: [],
    selectedPatternIds: [],
    knowledgeContext: '',
    experienceContext: '',
    knowledgeResults: [],
    experienceResults: [],
    reasons: ['test_local_route'],
    blockers: {},
    deterministic: true,
  };
}

function setRuntimeTestUser(): () => void {
  const originalRefreshUser = useUserStore.getState().refreshUser;
  useUserStore.setState({
    user: TEST_AUTH_USER,
    refreshUser: vi.fn(async () => undefined),
  });
  return () => useUserStore.setState({ refreshUser: originalRefreshUser });
}

const TEST_REPO_URL = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato';
const SECOND_REPO_URL = 'https://github.com/OuroborosCollective/Other-Studio';

function repoScopedJob(overrides: Record<string, unknown> = {}) {
  return {
    jobId: 'job_scoped',
    workspaceId: 'job_scoped',
    status: 'running' as const,
    repoUrl: TEST_REPO_URL,
    branch: 'main',
    runtimeId: 'conv_scoped',
    changedFiles: [] as string[],
    events: [],
    ...overrides,
  };
}

function repoScopedProjection(
  projectionState: SovereignLiveProjectionState = 'VISIBLE',
): SovereignLiveProjection {
  return {
    projectionId: `projection-${projectionState.toLowerCase()}`,
    eventId: `event-${projectionState.toLowerCase()}`,
    sessionId: TEST_CHAT_SESSION_ID,
    sessionBindingHash: '1'.repeat(64),
    attemptId: 'attempt-monitor-0123456789abcdef',
    runId: 'run-monitor',
    taskId: 'task-monitor',
    jobId: 'job_scoped',
    workspaceId: 'job_scoped',
    actionId: 'action-monitor',
    sourceKind: 'PROCESS',
    projectionKind: 'TERMINAL',
    projectionState,
    repositoryHead: '2'.repeat(40),
    sourceReceiptRef: '3'.repeat(64),
    sourceIdentityHash: '4'.repeat(64),
    payload: { chunk: 'monitor runtime output', processState: 'RUNNING' },
    projectionHash: '5'.repeat(64),
    authoritative: false,
    claim: 'OBSERVED',
  };
}

function repoScopedEvidenceAnchor(
  overrides: Partial<SovereignWorkspaceEvidenceAnchor> = {},
): SovereignWorkspaceEvidenceAnchor {
  return {
    anchorId: `evidence-${'a'.repeat(24)}`,
    jobId: 'job_scoped',
    workspaceId: 'job_scoped',
    claimKind: 'SOURCE_REVISION',
    verdict: 'VERIFIED',
    sourceVerdict: 'VERIFIED',
    sessionBindingHash: '1'.repeat(64),
    runId: 'run-monitor',
    taskId: 'task-monitor',
    attemptId: 'attempt-monitor-0123456789abcdef',
    actionId: 'action-monitor',
    scope: 'repository-runtime',
    sourceKind: 'TARGET_READBACK',
    sourceRefs: ['6'.repeat(64)],
    repositoryRevision: '7'.repeat(40),
    targetRevision: '7'.repeat(40),
    imageDigest: `sha256:${'8'.repeat(64)}`,
    runtimeIdentityHash: '9'.repeat(64),
    observedAt: '2026-08-25T00:00:00Z',
    freshnessReasons: [],
    evidenceHash: 'a'.repeat(64),
    authoritative: false,
    ...overrides,
  };
}

function openInspector(): void {
  if (screen.queryByTestId('monitor-runtime-action-trace')) return;
  fireEvent.click(screen.getByText('INSPECTOR'));
}

function getActionStream(): HTMLElement {
  openInspector();
  return screen.getByRole('log', { name: 'Sovereign Action Stream' });
}

async function loadRepoUrlFromChat(repoUrl: string): Promise<void> {
  fireEvent.change(chatField(), { target: { value: repoUrl } });
  fireEvent.click(sendButton());
  await waitFor(() => expect(screen.getByLabelText('Repo Inspector öffnen')).toBeDefined());
}

async function loadRepoFromChat(): Promise<void> {
  await loadRepoUrlFromChat(TEST_REPO_URL);
}

async function validateGitHubAccessFromLauncher(): Promise<void> {
  fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
  fireEvent.click(screen.getByLabelText('GitHub Access'));
  fireEvent.click(screen.getByText('Zugang eingeben'));
  fireEvent.change(screen.getByLabelText(/GitHub Token/i), { target: { value: fakeGitHubPat() } });
  fireEvent.click(screen.getByText('Übernehmen'));
  await waitFor(() =>
    expect(getActionStream()).toHaveTextContent('GitHub-Zugang bereit'),
  );
}


beforeEach(() => {
  testChatBubbleSequence = 0;
  testChatSession = {
    schemaVersion: 'sovereign.live-workspace-chat-session.v1',
    persistence: 'postgresql',
    sessionId: TEST_CHAT_SESSION_ID,
    repositoryIdentity: 'UNBOUND',
    repositoryBranch: 'main',
    recordedAt: '2026-08-23T00:00:00.000Z',
  };
  window.localStorage.clear();
  useUserStore.getState().clearUser();
  useUserStore.setState({ user: TEST_AUTH_USER });
  useToolchainStore.getState().reset();
  useSovereignToolInspectionStore.getState().resetEvidence();
  mockWorkerReply();
});

afterEach(() => {
  useUserStore.getState().clearUser();
  useToolchainStore.getState().reset();
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("BuilderContainer (AppControl DevChat shell)", () => {
  it("renders the AppControl DevChat shell structure", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    const root = screen.getByTestId("builder-container");
    expect(root).toHaveAttribute("data-layout", "chat-primary-agent-zero-background");
    expect(root).toHaveAttribute("aria-label", "Sovereign Builder");
    expect(screen.getAllByText("Sovereign").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Monitor")).toBeNull();
    expect(screen.getByLabelText("Sovereign Studio Tabs")).toBeDefined();
    expect(screen.getByText("CHAT")).toBeDefined();
    expect(screen.getByText("INSPECTOR")).toBeDefined();
    expect(screen.getByTestId("sovereign-chat-body-window")).toBeDefined();
    expect(screen.queryByTestId('live-workspace-monitor')).toBeNull();
    expect(screen.queryByTestId('live-workspace-monitor-desktop')).toBeNull();
    expect(screen.getByTestId('monitor-communication-dock')).toHaveAttribute('data-mode', 'chat');
    expect(screen.getByTestId('sovereign-chat-tool-row')).toBeDefined();
    expect(screen.queryByTestId('monitor-runtime-action-trace')).toBeNull();
    expect(chatField()).toBeDefined();
    expect(screen.getByLabelText("Menü")).toBeDefined();
  });

  it("loads the authenticated catalog into a compact, closed-by-default route picker", async () => {
    const fetchMock = mockFetchSequence();
    renderWithProviders(<BuilderContainer {...baseProps()} />);

    const trigger = screen.getByTestId('sovereign-llm-route-picker-trigger');
    expect(trigger).toHaveTextContent('Auto · Backend/Revolver');
    expect(screen.queryByRole('dialog', { name: 'LLM-Modell auswählen' })).toBeNull();

    fireEvent.click(trigger);
    const picker = await screen.findByRole('dialog', { name: 'LLM-Modell auswählen' });
    expect(within(picker).getByLabelText('Modelle durchsuchen')).toBeDefined();
    expect(within(picker).getByRole('option', {
      name: /FREE.*freellm.*deepseek-r1/i,
    })).toBeDefined();
    expect(fetchMock.mock.calls.some(([input]) => (
      isRoutePickerBootstrap(input as RequestInfo | URL)
    ))).toBe(true);
  });

  it("sends a manually pinned backend route without recording it as a PAL decision", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ choices: [{ message: { content: 'Manuelle Route antwortet.' } }], model: TEST_LITELLM_MODEL }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" />);

    const trigger = screen.getByTestId('sovereign-llm-route-picker-trigger');
    fireEvent.click(trigger);
    const picker = await screen.findByRole('dialog', { name: 'LLM-Modell auswählen' });
    fireEvent.click(within(picker).getByRole('option', {
      name: /FREE.*freellm.*deepseek-r1/i,
    }));
    expect(trigger).toHaveTextContent(/FREE · freellm · deepseek-r1/i);
    expect(screen.getByText(/Fixiert auf Backend-Route test-chat-route/i)).toBeDefined();

    fireEvent.change(chatField(), { target: { value: 'Welche Route nutzt du?' } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      requestUrl(input as RequestInfo | URL).includes('/api/llm/chat')
    ))).toBe(true));
    const chatCall = [...fetchMock.mock.calls].reverse().find(([input]) => (
      requestUrl(input as RequestInfo | URL).includes('/api/llm/chat')
    ));
    const body = JSON.parse(String(chatCall?.[1]?.body ?? '{}')) as { model?: string };
    expect(body.model).toBe('test-chat-route');

    fireEvent.click(screen.getByLabelText('Menü'));
    const sideMenu = screen.getByRole('dialog', { name: 'Sovereign Seitenmenü' });
    expect(within(sideMenu).queryByText(/PAL Verlauf/i)).toBeNull();
  });

  it("keeps chat primary and exposes a fresh workspace projection only through Inspector", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob()}
        agentProjections={[repoScopedProjection('VISIBLE')]}
        agentEvidenceAnchors={[repoScopedEvidenceAnchor()]}
      />,
    );

    fireEvent.change(chatField(), { target: { value: TEST_REPO_URL } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined());
    expect(screen.getByTestId('builder-container')).toHaveAttribute('data-layout', 'chat-primary-agent-zero-background');
    expect(screen.getByTestId('primary-surface-tab')).toHaveAttribute('data-primary-surface', 'chat');
    expect(screen.getByRole('button', { name: 'Sovereign Chat' })).toHaveTextContent('CHAT');
    expect(screen.queryByText('monitor runtime output')).toBeNull();
    expect(screen.queryByTestId('workspace-evidence-rail')).toBeNull();

    fireEvent.click(screen.getByText('INSPECTOR'));
    await waitFor(() => expect(screen.getByText('monitor runtime output')).toBeDefined());
    expect(screen.getByTestId('workspace-evidence-rail')).toBeDefined();
  });

  it("keeps a concise code-order clarification in the non-overlay monitor dock", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ choices: [{ message: { content: 'Provider prose must never reach the dock.' } }] }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob()}
        agentProjections={[repoScopedProjection('VISIBLE')]}
      />,
    );

    fireEvent.change(chatField(), { target: { value: TEST_REPO_URL } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByTestId('monitor-communication-dock')).toBeDefined());

    fireEvent.change(chatField(), { target: { value: 'Was kannst du?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Senden' }));

    await waitFor(() => expect(nonAuthFetchCalls(fetchMock).length).toBeGreaterThanOrEqual(3));
    await waitFor(() => expect(screen.getByText('Was kannst du?')).toBeDefined());
    expect(screen.queryByText('RUNTIME')).toBeNull();
    expect(screen.getByText('Welche konkrete Änderung soll ich umsetzen?')).toBeDefined();
    expect(screen.queryByText('Provider prose must never reach the dock.')).toBeNull();
    expect(screen.getByTestId('sovereign-chat-primary')).toBeDefined();
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(screen.getByTestId('monitor-communication-dock')).toHaveAttribute('data-mode', 'chat');
  });

  it("keeps chat primary when the only workspace projection is stale", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob()}
        agentProjections={[repoScopedProjection('STALE')]}
      />,
    );

    await loadRepoFromChat();

    expect(screen.getByTestId('sovereign-chat-primary')).toBeDefined();
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(chatField()).toBeDefined();
    expect(screen.getByTestId('primary-surface-tab')).toHaveAttribute('data-primary-surface', 'chat');
  });

  it("keeps user questions inside the chat when runtime waits for input", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob({ status: 'waiting-for-user' })}
        agentProjections={[repoScopedProjection('VISIBLE')]}
      />,
    );

    await loadRepoFromChat();

    expect(screen.getByTestId('sovereign-chat-primary')).toBeDefined();
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(chatField()).toBeDefined();
    expect(screen.getByRole('button', { name: 'Sovereign Chat' })).toHaveTextContent('CHAT');
  });

  it("keeps Workbench status vocabulary behind Inspector instead of surrounding the primary chat", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    expect(screen.queryByLabelText("Werkbank Status")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Actions:/ })).toBeNull();
    fireEvent.click(screen.getByText("INSPECTOR"));
    expect(screen.getByLabelText("Werkbank Status")).toBeDefined();
    expect(screen.getByRole("button", { name: /^Actions:/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^Changed:/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^Logs:/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^Errors:/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^Draft PR:/ })).toBeDefined();
  });

  it("keeps technical runtime module abbreviations hidden until the Inspector is explicitly opened", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    expect(screen.queryByText("ROU")).toBeNull();
    fireEvent.click(screen.getByText("INSPECTOR"));
    expect(screen.getAllByText("ROU").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Inspector (intern)")).toBeDefined();
    fireEvent.click(screen.getByText("INSPECTOR"));
    expect(screen.queryByText("ROU")).toBeNull();
  });

  it("shows explicit empty states for Actions, Files and Errors instead of fabricated data", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByText('INSPECTOR'));
    fireEvent.click(screen.getByRole("button", { name: /^Actions:/ }));
    expect(screen.getByText("Noch keine Actions")).toBeDefined();
    fireEvent.click(screen.getByLabelText("Schließen"));
    fireEvent.click(screen.getByRole("button", { name: /^Changed:/ }));
    expect(screen.getByText("Noch keine Änderungen")).toBeDefined();
    fireEvent.click(screen.getByLabelText("Schließen"));
    fireEvent.click(screen.getByRole("button", { name: /^Errors:/ }));
    expect(screen.getByText("Keine Fehler")).toBeDefined();
  });

  it("shows real changed files and a Draft PR opener only for the loaded repo", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob({
          changedFiles: ["src/App.tsx"],
          draftPrUrl: "https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1",
        })}
      />,
    );
    await loadRepoFromChat();
    fireEvent.click(screen.getByText('INSPECTOR'));
    fireEvent.click(screen.getByRole("button", { name: /^Changed:/ }));
    await waitFor(() => expect(screen.getByText("src/App.tsx")).toBeDefined());
    fireEvent.click(screen.getByLabelText("Schließen"));
    fireEvent.click(screen.getByRole("button", { name: /^Draft PR:/ }));
    expect(screen.getByText("Draft PR öffnen")).toBeDefined();
  });

  it("keeps the default builder surface quiet and chat-first", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    expect(screen.queryByText("Sovereign Studio")).toBeNull();
    expect(screen.queryByText("Planner")).toBeNull();
    expect(screen.queryByText("Changes")).toBeNull();
    expect(screen.queryByText("Code")).toBeNull();
    expect(screen.getByRole("tab", { name: /Terminal/i })).toBeDisabled();
    expect(screen.getByTestId("sovereign-chat-body-window")).toBeDefined();
    expect(screen.queryByText(/Sovereign geführter Chat Ablauf/i)).toBeNull();
  });

  it("keeps the monitor free of legacy simulated runtime text", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    expect(screen.getAllByText(/Repo fehlt/).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Package summary")).toBeNull();
    expect(screen.queryByText(/AutoSwitchOrchestrator/)).toBeNull();
    expect(screen.queryByText(/simulate/i)).toBeNull();
  });

  it("shows guided suggestions only in the empty primary chat", () => {
    const props = baseProps();
    renderWithProviders(<BuilderContainer {...props} mission="" />);
    expect(screen.getByTestId('sovereign-action-suggestion-strip')).toBeDefined();
    expect(screen.getByLabelText('Tool Launcher öffnen')).toBeDefined();
    expect(screen.queryByText("Let's build!")).toBeNull();
    expect(screen.getByTestId('monitor-communication-dock')).toHaveAttribute('data-mode', 'chat');
    expect(screen.queryByTestId('monitor-runtime-action-trace')).toBeNull();
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it("keeps runtime action receipts available behind Inspector instead of crowding the chat", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" />);

    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Repo' }));
    expect(screen.queryByRole('log', { name: 'Sovereign Action Stream' })).toBeNull();
    fireEvent.click(screen.getByText('INSPECTOR'));

    const actionStream = screen.getByRole('log', { name: 'Sovereign Action Stream' });
    expect(screen.getByTestId('monitor-runtime-action-trace')).toContainElement(actionStream);
    expect(actionStream).toHaveTextContent('Repo-Setup geöffnet');
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
  });

  it("shows integration intent draft card for normal text inputs when repo is ready", async () => {
    const props = baseProps();
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ choices: [{ message: { content: JSON.stringify({
        mode: 'action',
        intent: 'code_execution',
        action_disposition: 'review',
        clarification_code: 'none',
        is_startup: false,
        confidence: 0.95,
        language: 'de',
      }) } }], model: 'deepseek-r1' }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} agentReady={false} />);
    await loadRepoFromChat();
    fireEvent.change(chatField(), { target: { value: "Bitte mobile UX verbessern und Log direkt sichtbar machen." } });
    expect(sendButton()).not.toBeDisabled();
    fireEvent.click(sendButton());
    expect(chatField().value).toBe("");
    // Issue #520: Normal text with repo loaded shows draft card instead of routing to Worker
    await waitFor(() => expect(screen.getByTestId("integration-intent-draft-card")).toBeInTheDocument());
    expect(screen.getByTestId('sovereign-chat-primary')).toHaveStyle({
      overflowY: 'auto',
      overflowX: 'hidden',
    });
    expect(screen.getByText('Freigabe für exakt diesen Repository-Auftrag:')).toBeInTheDocument();
    expect(screen.getByTestId('draft-execution-mission')).toHaveTextContent(
      'Bitte mobile UX verbessern und Log direkt sichtbar machen.',
    );
  });

  it("dispatches exactly the visible mission and revision only after a separate owner confirmation", async () => {
    const props = {
      ...baseProps(),
      agentReady: true,
      agentJob: repoScopedJob({ status: 'completed' }),
      onStartAgent: vi.fn(),
    };
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ choices: [{ message: { content: JSON.stringify({
        mode: 'action',
        intent: 'code_execution',
        action_disposition: 'review',
        clarification_code: 'none',
        is_startup: false,
        confidence: 0.96,
        language: 'de',
      }) } }], model: 'deepseek-r1' }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );

    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();

    const originalText = 'Verbessere die mobile Chat-UX und prüfe den Runtime-Pfad.';
    fireEvent.change(chatField(), { target: { value: originalText } });
    fireEvent.click(sendButton());
    const draftCard = await screen.findByTestId('integration-intent-draft-card');

    expect(within(draftCard).getByTestId('draft-execution-mission').textContent).toBe(originalText);
    expect(within(draftCard).getByTestId('draft-target-repo').textContent).toBe(TEST_REPO_URL);
    expect(within(draftCard).getByTestId('draft-target-branch').textContent).toBe('main');
    expect(within(draftCard).getByTestId('draft-target-head').textContent).toBe('c'.repeat(40));
    expect(props.onStartAgent).not.toHaveBeenCalled();

    fireEvent.click(within(draftCard).getByRole('button', { name: 'Sicheren GitHub-Zugang öffnen' }));
    fireEvent.click(screen.getByText('Zugang eingeben'));
    fireEvent.change(screen.getByLabelText(/GitHub Token/i), { target: { value: fakeGitHubPat() } });
    fireEvent.click(screen.getByText('Übernehmen'));
    await waitFor(() => expect(
      getActionStream(),
    ).toHaveTextContent('GitHub-Zugang bereit'));

    // Access capability is not consent to execute. The exact preview stays pending.
    expect(props.onStartAgent).not.toHaveBeenCalled();
    expect(screen.getByTestId('integration-intent-draft-card')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Repository-Auftrag starten' }));
    await waitFor(() => expect(props.onStartAgent).toHaveBeenCalledOnce());
    expect(props.onMissionChange).toHaveBeenCalledWith(originalText);
    expect(props.onStartAgent).toHaveBeenCalledWith(originalText, {
      repoUrl: TEST_REPO_URL,
      branch: 'main',
      expectedHeadSha: 'c'.repeat(40),
      githubAccessToken: fakeGitHubPat(),
    });
  });

  it("syncs externally adopted insight missions only into an untouched empty composer", () => {
    const props = baseProps();
    const { rerender } = renderWithProviders(<BuilderContainer {...props} mission="" />);
    const adoptedMission = [
      "Ideenfabrik Auftrag:",
      "Verbessere mobile UX und Log-Fenster.",
      "",
      "Repository-Kontext:",
      "Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert zu werden.",
      "",
      "Umsetzung:",
      "- Erzeuge echte Änderungen im passenden Codepfad.",
    ].join("\n");
    // rerender already has Provider context from initial render
    rerender(<BuilderContainer {...props} mission={adoptedMission} />);
    expect(chatField().value).toBe("Verbessere mobile UX und Log-Fenster.");
  });

  it("keeps the approved online mission byte-for-byte unchanged", async () => {
    const props = { ...baseProps(), agentReady: true, agentJob: repoScopedJob({ status: 'completed' }), onStartAgent: vi.fn() };
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();

    const originalText = "Bitte Sovereign Agent: implementiere den mobilen Chat-Fix als Draft PR.";
    fireEvent.change(chatField(), { target: { value: originalText } });
    fireEvent.click(sendButton());

    const draftCard = await screen.findByTestId('integration-intent-draft-card');
    expect(within(draftCard).getByTestId('draft-execution-mission').textContent).toBe(originalText);
    expect(props.onMissionChange).not.toHaveBeenCalled();
    expect(props.onStartAgent).not.toHaveBeenCalled();

    fireEvent.click(within(draftCard).getByRole('button', { name: 'Repository-Auftrag starten' }));
    await waitFor(() => expect(props.onStartAgent).toHaveBeenCalledOnce());
    expect(props.onMissionChange).toHaveBeenCalledWith(originalText);
    expect(props.onStartAgent.mock.calls[0][0]).toBe(originalText);
    expect(props.onStartAgent.mock.calls[0][0]).not.toContain('Ideenfabrik Auftrag:');
  });

  it("opens the DevChat side menu without duplicating raw runtime endpoints", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    expect(screen.queryByText("Sovereign Studio")).toBeNull();
    fireEvent.click(screen.getByLabelText("Menü"));
    const sideMenu = screen.getByRole("dialog", { name: "Sovereign Seitenmenü" });
    expect(screen.getByText("Sovereign Studio")).toBeDefined();
    expect(within(sideMenu).queryByText(/Cloudflare Workers/i)).toBeNull();
    expect(within(sideMenu).queryByText(/workers\.dev/i)).toBeNull();
    expect(within(sideMenu).getByText(/Auftrag analysieren/i)).toBeDefined();
  });

  it("side menu exposes the registered launcher and does not offer an empty chat export", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Menü"));
    const sideMenu = screen.getByRole("dialog", { name: "Sovereign Seitenmenü" });
    expect(screen.getByTestId("sovereign-side-menu-panel")).toHaveStyle({ overflowY: "auto" });

    expect(within(sideMenu).getByRole("button", { name: /Chat teilen/i })).toBeDisabled();
    expect(within(sideMenu).getByTestId("builder__draft-pr")).toHaveAttribute("data-gate-state", "repo-required");

    fireEvent.click(within(sideMenu).getByRole("button", { name: /Alle Tools/i }));
    expect(screen.queryByRole("dialog", { name: "Sovereign Seitenmenü" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "Sovereign Launcher" })).toBeDefined();
  });

  it("side menu analysis actions use the real repo gate instead of legacy direct callbacks", async () => {
    const props = baseProps();
    renderWithProviders(<BuilderContainer {...props} />);
    fireEvent.click(screen.getByLabelText("Menü"));
    const sideMenu = screen.getByRole("dialog", { name: "Sovereign Seitenmenü" });

    fireEvent.click(within(sideMenu).getByRole("button", { name: "Auftrag analysieren" }));

    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: "Repo Setup" })).toBeDefined(),
    );
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
    expect(getActionStream())
      .toHaveTextContent("Preset wartet auf Repo: Features");
  });

  it("side menu Runtime Logs opens the real evidence sheet without fabricating entries", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Menü"));
    const sideMenu = screen.getByRole("dialog", { name: "Sovereign Seitenmenü" });
    fireEvent.click(within(sideMenu).getByRole("button", { name: /Runtime Logs/i }));

    expect(screen.queryByRole("dialog", { name: "Sovereign Seitenmenü" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "Runtime Evidence Logs" })).toBeDefined();
    expect(screen.getByText("Noch keine Runtime-Ereignisse.")).toBeDefined();
  });

  it("side menu reports PAL history without claiming an active route and disables Draft PR without change evidence", async () => {
    const props = baseProps();
    mockFetchSequence(jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();

    fireEvent.click(screen.getByLabelText("Menü"));
    const sideMenu = screen.getByRole("dialog", { name: "Sovereign Seitenmenü" });
    expect(within(sideMenu).getByText(/1 belegte Entscheidung/i)).toBeDefined();
    expect(within(sideMenu).getByText(/Referenzschätzung:/i)).toBeDefined();
    expect(within(sideMenu).getByText(/Modelle konfiguriert/i)).toBeDefined();
    expect(within(sideMenu).queryByText(/sparsame Route aktiv/i)).toBeNull();

    const draftButton = within(sideMenu).getByTestId("builder__draft-pr");
    expect(draftButton).toBeDisabled();
    expect(draftButton).toHaveAttribute("data-gate-state", "evidence-required");
    expect(props.onPublishDraftPr).not.toHaveBeenCalled();
  });

  it("side menu records an Agent cancel request without claiming the Agent already stopped", async () => {
    const onCancelAgent = vi.fn();
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob()}
        onCancelAgent={onCancelAgent}
      />,
    );
    await loadRepoFromChat();

    fireEvent.click(screen.getByLabelText("Menü"));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Sovereign Seitenmenü" }))
      .getByRole("button", { name: /Agent stoppen/i }));

    expect(onCancelAgent).toHaveBeenCalledOnce();
    const actionStream = getActionStream();
    expect(actionStream).toHaveTextContent("Agent-Abbruch angefragt");
    expect(actionStream).not.toHaveTextContent("Agent gestoppt");
  });

  it("side menu routes Draft PR through GitHub access and publishes only when all evidence is ready", async () => {
    const props = baseProps();
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );
    renderWithProviders(
      <BuilderContainer
        {...props}
        mission=""
        repoReady={false}
        agentJob={repoScopedJob({ status: 'completed', changedFiles: ["README.md"] })}
      />,
    );
    await loadRepoFromChat();

    fireEvent.click(screen.getByLabelText("Menü"));
    let sideMenu = screen.getByRole("dialog", { name: "Sovereign Seitenmenü" });
    let draftButton = within(sideMenu).getByTestId("builder__draft-pr");
    expect(draftButton).toHaveAttribute("data-gate-state", "access-required");
    fireEvent.click(draftButton);
    expect(props.onPublishDraftPr).not.toHaveBeenCalled();
    expect(screen.getByText(/GitHub-Zugang fehlt/i)).toBeDefined();

    await validateGitHubAccessFromLauncher();
    fireEvent.click(screen.getByLabelText("Menü"));
    sideMenu = screen.getByRole("dialog", { name: "Sovereign Seitenmenü" });
    draftButton = within(sideMenu).getByTestId("builder__draft-pr");
    expect(draftButton).toHaveAttribute("data-gate-state", "ready");
    fireEvent.click(draftButton);

    expect(await screen.findByTestId("draft-pr-action-preview")).toBeDefined();
    expect(props.onPublishDraftPr).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("confirm-draft-pr-action-preview"));

    await waitFor(() => expect(props.onPublishDraftPr).toHaveBeenCalledOnce());
    expect(props.onPublishDraftPr).toHaveBeenCalledWith(expect.objectContaining({
      repoUrl: TEST_REPO_URL,
      branch: 'main',
      changes: [],
      confirmed: true,
    }));
    expect(getActionStream()).toHaveTextContent("Bestätigte Änderungen werden übergeben");
  });

  it("keeps Worker runtime sources unknown until health or response evidence exists", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} agentReady onStartAgent={vi.fn()} />);
    fireEvent.click(screen.getByText('INSPECTOR'));
    const rtButton = screen.getByRole("button", { name: /RT.*Runtime Quelle/i });
    expect(rtButton).toHaveAttribute("title", "Runtime Quelle");
    fireEvent.click(rtButton);
    expect(screen.getByText("Runtime Quelle")).toBeDefined();
    expect(screen.getByText("LLM Runtime nicht geprüft")).toBeDefined();
    expect(screen.getByText("Noch keine Health- oder Response-Evidence für diese Sitzung.")).toBeDefined();
    expect(screen.getByText("Worker KV konfiguriert")).toBeDefined();
    expect(screen.getByText("Modellkatalog konfiguriert")).toBeDefined();
    expect(screen.getByText("Interne Sovereign Agent Runtime für Code/Draft-PR-Aufträge")).toBeDefined();
  });

  it("promotes the LLM runtime source only after a successful direct LLM response", async () => {
    const restoreUser = setRuntimeTestUser();
    let rejectInference: ((reason?: unknown) => void) | null = null;
    vi.spyOn(areInferenceApi, 'evaluateAreInference').mockImplementation(
      () => new Promise<never>((_resolve, reject) => { rejectInference = reject; }),
    );
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      return runtimeSupportResponse(url, init)
        ?? jsonResponse({ choices: [{ message: { content: 'unused' } }] });
    });
    vi.stubGlobal('fetch', fetchMock);

    try {
      renderWithProviders(<BuilderContainer {...baseProps()} mission="" agentReady />);
      fireEvent.change(chatField(), { target: { value: 'Was bedeutet Runtime-Evidence?' } });
      fireEvent.click(sendButton());

      await waitFor(() => expect(fetchMock.mock.calls.some(([input]) =>
        requestUrl(input as RequestInfo | URL).includes('/api/llm/chat'),
      )).toBe(true));
      fireEvent.click(screen.getByText('INSPECTOR'));
      fireEvent.click(screen.getByRole("button", { name: /RT.*Runtime Quelle/i }));
      await waitFor(() => expect(screen.getByText("LLM Runtime")).toBeDefined());
      expect(screen.queryByText("LLM Runtime nicht geprüft")).toBeNull();
    } finally {
      await act(async () => {
        rejectInference?.(new Error('Sovereign LLM evidence assertion completed.'));
        await Promise.resolve();
      });
      restoreUser();
    }
  });

  it("keeps consecutive strict-contract submits independent without offline learning", async () => {
    const restoreUser = setRuntimeTestUser();
    const inferenceSpy = vi.spyOn(areInferenceApi, 'evaluateAreInference');
    const fetchMock = mockFetchSequence(
      jsonResponse({ choices: [{ message: { content: 'first strict reply' } }] }),
      jsonResponse({ choices: [{ message: { content: 'second strict reply' } }] }),
    );
    const llmCalls = () => fetchMock.mock.calls.filter(([input]) => (
      requestUrl(input as RequestInfo | URL).includes('/api/llm/chat')
    ));

    try {
      renderWithProviders(<BuilderContainer {...baseProps()} mission="" agentReady />);
      fireEvent.change(chatField(), { target: { value: 'Erkläre mir die Runtime-Evidence.' } });
      fireEvent.click(sendButton());

      await waitFor(() => expect(llmCalls()).toHaveLength(1));
      await waitFor(() => expect(
        screen.getAllByText('Welche konkrete Änderung soll ich umsetzen?').length,
      ).toBeGreaterThan(0));

      const secondMessage = 'Diese zweite Nachricht darf nicht verloren gehen.';
      fireEvent.change(chatField(), { target: { value: secondMessage } });
      fireEvent.click(sendButton());

      await waitFor(() => expect(llmCalls()).toHaveLength(2));
      expect(screen.getAllByText(secondMessage).length).toBeGreaterThanOrEqual(1);
      expect(chatField().value).toBe('');
      expect(inferenceSpy).not.toHaveBeenCalled();
    } finally {
      restoreUser();
    }
  });


  it("replaces successful direct LLM response evidence with the latest failed call", async () => {
    const restoreUser = setRuntimeTestUser();
    vi.spyOn(areInferenceApi, 'evaluateAreInference').mockImplementation(
      (input) => Promise.resolve(localAreInferenceResult(input.onlineAvailable)),
    );
    let chatCalls = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url.includes('/api/llm/routes')) return liteLlmRouteCatalogResponse();
      if (url.includes('/api/llm/chat')) {
        chatCalls += 1;
        if (chatCalls === 1) {
          const userText = lastUserTextFromLiteLlmRequest(init);
          return jsonResponse({
            model: TEST_LITELLM_MODEL,
            choices: [{ message: { content: JSON.stringify(testIntentEnvelope(
              userText,
              'Der erste Sovereign LLM-Aufruf war erfolgreich.',
            )) } }],
          });
        }
        return jsonResponse({ error: 'freellm_upstream_unavailable' }, 503);
      }
      return runtimeSupportResponse(url, init)
        ?? jsonResponse({ choices: [{ message: { content: 'unused' } }] });
    }));

    try {
      renderWithProviders(<BuilderContainer {...baseProps()} mission="" agentReady />);
      fireEvent.change(chatField(), { target: { value: 'Erkläre mir den ersten Runtime-State.' } });
      fireEvent.click(sendButton());
      await waitFor(() => expect(chatCalls).toBe(1));
      expect((await screen.findAllByText('Welche konkrete Änderung soll ich umsetzen?')).length).toBeGreaterThanOrEqual(1);

      fireEvent.change(chatField(), { target: { value: 'Erkläre mir den neuen Runtime-State.' } });
      fireEvent.click(sendButton());
      await waitFor(() =>
        expect(screen.getAllByText(/Codeauftragsvertrag blockiert|sichere Online-Aktionsroute ist blockiert/i).length).toBeGreaterThan(0),
      );
      expect(chatCalls).toBe(2);

      fireEvent.click(screen.getByText('INSPECTOR'));
      fireEvent.click(screen.getByRole('button', { name: /RT.*Runtime Quelle/i }));
      await waitFor(() => expect(screen.getByText('LLM Runtime blockiert')).toBeDefined());
    } finally {
      restoreUser();
    }
  });

  it("never starts a recognized code order before the visible review is confirmed", async () => {
    const props = { ...baseProps(), agentReady: true, agentJob: repoScopedJob({ status: 'completed' }), onStartAgent: vi.fn() };
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();

    const originalText = "Bitte implementiere einen Chat-State-Fix als Draft PR.";
    fireEvent.change(chatField(), { target: { value: originalText } });
    fireEvent.click(sendButton());

    const draftCard = await screen.findByTestId('integration-intent-draft-card');
    expect(props.onStartAgent).not.toHaveBeenCalled();
    expect(within(draftCard).getByTestId('draft-execution-mission').textContent).toBe(originalText);

    fireEvent.click(within(draftCard).getByRole('button', { name: 'Repository-Auftrag starten' }));
    await waitFor(() => expect(props.onStartAgent).toHaveBeenCalledOnce());
    expect(props.onStartAgent).toHaveBeenCalledWith(originalText, {
      repoUrl: TEST_REPO_URL,
      branch: "main",
      expectedHeadSha: 'c'.repeat(40),
      githubAccessToken: fakeGitHubPat(),
    });
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
  });

  it("returns one fixed clarification instead of answering a README conversation", async () => {
    const props = { ...baseProps(), agentReady: true, onStartAgent: vi.fn() };
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ choices: [{ message: { content: "README-Inhalt erklärt." } }] }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();

    fireEvent.change(chatField(), { target: { value: "Was ist der Inhalt der README?" } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(nonAuthFetchCalls(fetchMock)).toHaveLength(3));
    expect((await screen.findAllByText("Welche konkrete Änderung soll ich umsetzen?")).length)
      .toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("README-Inhalt erklärt.")).toBeNull();
    expect(props.onStartAgent).not.toHaveBeenCalled();
    expect(screen.queryByTestId('integration-intent-draft-card')).toBeNull();
  });

  it("does not treat a Pull Request explanation as an execution order", async () => {
    const props = { ...baseProps(), agentReady: true, onStartAgent: vi.fn() };
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ choices: [{ message: { content: "Ein Pull Request ist eine prüfbare Änderung." } }] }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();

    fireEvent.change(chatField(), { target: { value: "Was ist ein Pull Request?" } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(nonAuthFetchCalls(fetchMock)).toHaveLength(3));
    expect((await screen.findAllByText("Welche konkrete Änderung soll ich umsetzen?")).length)
      .toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Ein Pull Request ist eine prüfbare Änderung.")).toBeNull();
    expect(props.onStartAgent).not.toHaveBeenCalled();
    expect(screen.queryByTestId('integration-intent-draft-card')).toBeNull();
  });


  it("does not call the protected direct LLM route for a guest session", async () => {
    const originalRefreshUser = useUserStore.getState().refreshUser;
    useUserStore.setState({
      user: null,
      refreshUser: vi.fn(async () => undefined),
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (isAuthBootstrapRequest(input)) return jsonResponse({ error: 'not authenticated' }, 401);
      return runtimeSupportResponse(url, init) ?? jsonResponse({ ok: true });
    });
    vi.stubGlobal('fetch', fetchMock);

    try {
      renderWithProviders(<BuilderContainer {...baseProps()} mission="" agentReady />);
      fireEvent.change(chatField(), { target: { value: "Erkläre mir den Runtime-State." } });
      fireEvent.click(sendButton());

      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.queryByText(/bestätigte Anmeldung erforderlich/i)).toBeNull();
      expect(fetchMock.mock.calls.some(([input]) =>
        requestUrl(input as RequestInfo | URL).includes('/api/llm/chat'),
      )).toBe(false);
      expect(fetchMock.mock.calls.some(([input]) =>
        requestUrl(input as RequestInfo | URL).includes('/api/llm/routes'),
      )).toBe(false);
    } finally {
      useUserStore.setState({ refreshUser: originalRefreshUser });
    }
  });


  it("loads a GitHub repo as runtime context without writing analysis into the composer", async () => {
    const props = baseProps();
    mockFetchSequence(jsonResponse({ tree: [
      { path: "src/App.tsx", type: "blob", size: 123 },
      { path: "src/features/product/containers/BuilderContainer.tsx", type: "blob", size: 456 },
    ], truncated: false }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    const repoUrl = "https://github.com/OuroborosCollective/Sovereign-Studio-ato/tree/main/src";
    fireEvent.change(chatField(), { target: { value: repoUrl } });
    fireEvent.click(sendButton());
    expect(chatField().value).toBe("");
    await waitFor(() => expect(screen.getByLabelText('Repo Inspector öffnen')).toBeDefined());
    expect(screen.getAllByText(repoUrl).length).toBeGreaterThanOrEqual(1);
    expect(chatField().value).not.toContain("Repo geladen");
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });


  it("does not publish internal provider material into monitor communication", async () => {
    const rawProviderText = "System prompt: hidden provider payload";
    const fetchMock = mockFetchSequence(jsonResponse({
      choices: [{ message: { content: rawProviderText } }],
      model: TEST_LITELLM_MODEL,
    }));
    renderWithProviders(<BuilderContainer {...baseProps()} />);

    fireEvent.change(chatField(), { target: { value: "Prüfe die Monitor-Ausgabe." } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(nonAuthFetchCalls(fetchMock)).toHaveLength(2));
    expect(screen.getByTestId('monitor-communication-bubbles')).not.toHaveTextContent(rawProviderText);
  });


  it("keeps scoped Sovereign Agent output as plain hints and not result cards", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob({ changedFiles: ["src/App.tsx"] })}
      />,
    );
    await loadRepoFromChat();
    expect(screen.queryByTestId('agent-event-stream')).toBeNull();
    fireEvent.click(screen.getByText('INSPECTOR'));
    expect(screen.getByTestId('agent-event-stream')).toBeDefined();
    expect(screen.getByText('Sovereign Agent arbeitet…')).toBeDefined();
    expect(screen.getByText('Dateien: 1')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Repo Datei öffnen: src/App.tsx' })).toBeDefined();
    expect(screen.queryByLabelText(/Karten/i)).toBeNull();
  });

  it("shows slash command menu and runs selected command with Enter", () => {
    const props = baseProps();
    renderWithProviders(<BuilderContainer {...props} />);
    fireEvent.change(chatField(), { target: { value: "/a" } });
    expect(screen.getByTestId("slash-command-menu")).toBeDefined();
    expect(screen.getByText("/analyze")).toBeDefined();
    fireEvent.keyDown(chatField(), { key: "Enter", code: "Enter" });
    expect(props.onGenerateIdeas).toHaveBeenCalledOnce();
    expect(chatField().value).toBe("");
    expect(screen.queryByTestId("slash-command-menu")).toBeNull();
  });

  it("closes slash command popup on Escape without submitting", () => {
    const props = baseProps();
    renderWithProviders(<BuilderContainer {...props} />);
    fireEvent.change(chatField(), { target: { value: "/" } });
    expect(screen.getByTestId("slash-command-menu")).toBeDefined();
    fireEvent.keyDown(chatField(), { key: "Escape", code: "Escape" });
    expect(screen.queryByTestId("slash-command-menu")).toBeNull();
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
    expect(props.onGenerateErrorWorkflow).not.toHaveBeenCalled();
    expect(props.onPublishDraftPr).not.toHaveBeenCalled();
  });

  it("runs /repo through the existing repo load path", async () => {
    const props = baseProps();
    mockFetchSequence(jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 123 }, { path: "README.md", type: "blob", size: 42 }], truncated: false }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    fireEvent.change(chatField(), { target: { value: "/repo https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByLabelText('Repo Inspector öffnen')).toBeDefined());
    expect(chatField().value).toBe("");
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it("mounts repo split inspector only after a real repo snapshot is loaded", async () => {
    const props = baseProps();
    mockFetchSequence(jsonResponse({ tree: [
      { path: "src/App.tsx", type: "blob", size: 123 },
      { path: "README.md", type: "blob", size: 42 },
    ], truncated: false }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);

    expect(screen.queryByTestId("repo-split-inspector")).toBeNull();
    fireEvent.change(chatField(), { target: { value: "https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(screen.getByLabelText('Repo Inspector öffnen')).toBeDefined());
    expect(screen.queryByTestId("repo-split-inspector")).toBeNull();
    openInspector();
    await waitFor(() => expect(screen.getByTestId("repo-split-inspector")).toBeDefined());
    expect(screen.getByRole("navigation", { name: "Repo Baum Split Inspector", hidden: true })).toBeDefined();
    expect(screen.queryByTestId("repo-tree-explorer")).toBeNull();
    expect(screen.getByTestId("builder-container")).toHaveClass("sovereign-builder-container--repo-ready");
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it("opens repo tree inspector from the loaded repo label and fills composer on file tap", async () => {
    const props = baseProps();
    mockFetchSequence(jsonResponse({ tree: [
      { path: "src/App.tsx", type: "blob", size: 123 },
      { path: "src/features/product/containers/BuilderContainer.tsx", type: "blob", size: 456 },
      { path: "README.md", type: "blob", size: 42 },
    ], truncated: false }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    fireEvent.change(chatField(), { target: { value: "https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByLabelText('Repo Inspector öffnen')).toBeDefined());
    fireEvent.click(screen.getByLabelText("Repo Inspector öffnen"));
    const dialog = screen.getByTestId("repo-tree-explorer");
    expect(dialog).toBeDefined();
    fireEvent.click(within(dialog).getByText("App.tsx"));
    expect(chatField().value).toContain("Erkläre mir src/App.tsx");
    expect(props.onMissionChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId("repo-tree-explorer")).toBeNull();
  });

  it("does not fabricate assistant file badges for a repo-load status event", async () => {
    const props = baseProps();
    mockFetchSequence(jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 123 }, { path: "README.md", type: "blob", size: 42 }], truncated: false }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    fireEvent.change(chatField(), { target: { value: "https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByLabelText('Repo Inspector öffnen')).toBeDefined());
    expect(screen.queryByLabelText("Repo Datei öffnen: src/App.tsx")).toBeNull();
    expect(chatField().value).toBe("");
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it("shows publishing state correctly", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} isPublishing />);
    expect(sendButton()).toBeDisabled();
  });

  it("recognizes a pasted GitHub URL with a local load hint without auto-submitting", () => {
    const props = baseProps();
    const fetchMock = mockFetchSequence(jsonResponse({ choices: [{ message: { content: "unused" } }] }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    fireEvent.change(chatField(), { target: { value: "https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    expect(screen.getByText("Repo erkannt · Laden")).toBeTruthy();
    expect(nonAuthFetchCalls(fetchMock)).toHaveLength(0);
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it("keeps committed mission text in monitor communication without a legacy bubble context menu", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.change(chatField(), { target: { value: "Beobachtbare Mission" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByText("Beobachtbare Mission")).toBeDefined());
    expect(screen.getByTestId('monitor-communication-bubbles')).toBeDefined();
    expect(screen.queryByText("📋 Kopieren")).toBeNull();
    expect(screen.queryByText("💬 Zitieren")).toBeNull();
  });

  it("accepts a follow-up directly in the monitor dock without reopening chat", async () => {
    const props = baseProps();
    renderWithProviders(<BuilderContainer {...props} />);
    fireEvent.change(chatField(), { target: { value: "Erste Monitor-Mission" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByText("Erste Monitor-Mission")).toBeDefined());
    fireEvent.change(chatField(), { target: { value: "Direkte Folgefrage im Monitor" } });
    expect(chatField().value).toBe("Direkte Folgefrage im Monitor");
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it("keeps primary Android chat controls at least 44px and technical controls bounded to Inspector", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);

    expect(screen.getByLabelText("Menü")).toHaveStyle({ width: "44px", height: "44px" });
    expect(screen.getByLabelText("Profil")).toHaveStyle({ width: "44px", height: "44px" });
    expect(screen.queryByRole("button", { name: /RT.*Runtime Quelle/i })).toBeNull();
    expect(screen.queryByLabelText("Panel öffnen")).toBeNull();
    expect(chatField()).toHaveStyle({ minHeight: "44px" });
    expect(sendButton()).toHaveStyle({ width: "44px", height: "44px" });

    fireEvent.click(screen.getByText("INSPECTOR"));
    expect(screen.getByRole("button", { name: /RT.*Runtime Quelle/i })).toHaveStyle({ minHeight: "44px" });
    expect(screen.getByLabelText("Panel öffnen")).toHaveStyle({ minWidth: "44px", minHeight: "44px" });
    expect(screen.getByRole("button", { name: /^Actions:/ })).toHaveStyle({ minHeight: "44px" });

    fireEvent.click(screen.getByLabelText("Menü"));
    expect(screen.getByLabelText("Menü schließen")).toHaveStyle({ minWidth: "44px", minHeight: "44px" });
  });

  it("uses a responsive tablet/phone shell width instead of a hard phone-only cap", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    const container = screen.getByTestId("builder-container");
    expect(container.style.maxWidth).toBe("");
    expect(container.className).toContain("sovereign-builder-container");
    expect(document.body.innerHTML).toMatch(
      /\.sovereign-builder-container\s*\{\s*max-width:\s*100vw;?\s*\}/,
    );
    expect(document.body.innerHTML).toMatch(/@media \(min-width: 1180px\)/);
  });

  // ── Phase 1 spec: Executor / delegation / security tests ────────────────────

  it("blocks GitHub PAT from chat, shows SecurityBlockCard with action button, never stores token in chat", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    const pat = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef01";
    fireEvent.change(chatField(), { target: { value: pat } });
    fireEvent.click(sendButton());
    // SecurityBlockCard renders the card title from evaluateInputPolicy
    await waitFor(() =>
      expect(screen.getByText(/Sicherer GitHub-Zugang erkannt/i)).toBeDefined(),
    );
    // Must show the secure-access action button
    expect(screen.getByText(/GitHub-Zugang öffnen/i)).toBeDefined();
    // Token must not appear in rendered chat bubbles
    expect(screen.queryByText(pat)).toBeNull();
  });

  it("security card never instructs user to enter token in chat", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.change(chatField(), { target: { value: "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef01" } });
    fireEvent.click(sendButton());
    await waitFor(() =>
      expect(screen.getByText(/Sicherer GitHub-Zugang erkannt/i)).toBeDefined(),
    );
    // Must NOT say "Token im Kanal eingeben"
    expect(screen.queryByText(/Token im Kanal/i)).toBeNull();
    // Must NOT say "sicheres Zugangsfeld" as a plain chatline (old wording)
    // Card button exists instead
    expect(screen.getByText(/GitHub-Zugang öffnen/i)).toBeDefined();
  });

  it("requests Sovereign Agent job start without claiming a confirmed running job", async () => {
    const props = { ...baseProps(), agentReady: true, agentJob: repoScopedJob({ status: 'completed' }), onStartAgent: vi.fn() };
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();
    fireEvent.change(chatField(), { target: { value: "Implementiere den mobilen Chat-Fix als Draft PR." } });
    fireEvent.click(sendButton());
    const draftCard = await screen.findByTestId('integration-intent-draft-card');
    expect(props.onStartAgent).not.toHaveBeenCalled();
    fireEvent.click(within(draftCard).getByRole('button', { name: 'Repository-Auftrag starten' }));
    await waitFor(() =>
      expect(getActionStream())
        .toHaveTextContent("Freigegebener Repository-Auftrag angefragt"),
    );
    await waitFor(() => expect(props.onStartAgent).toHaveBeenCalledOnce());
    expect(screen.queryByText(/Sovereign Agent Runtime wird gestartet/i)).toBeNull();
    await waitFor(() => expect(screen.getAllByText(/kein Auto-Merge/i).length).toBeGreaterThan(0));
  });

  it("ignores a direct duplicate Agent start while the first start is still in flight", async () => {
    let resolveStart: (() => void) | null = null;
    const onStartAgent = vi.fn(
      () => new Promise<void>((resolve) => {
        resolveStart = resolve;
      }),
    );
    const props = { ...baseProps(), agentReady: true, agentJob: repoScopedJob({ status: 'completed' }), onStartAgent };
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );

    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();

    fireEvent.change(chatField(), {
      target: { value: "Implementiere den mobilen Chat-Fix als Draft PR mit Regressionstest." },
    });
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Executor" }));
    await waitFor(() => expect(onStartAgent).toHaveBeenCalledOnce());

    try {
      const launcherOpenButton = screen.queryByLabelText("Tool Launcher öffnen");
      if (launcherOpenButton) fireEvent.click(launcherOpenButton);
      fireEvent.click(screen.getByRole("menuitem", { name: "Executor" }));
      await act(async () => {
        await Promise.resolve();
      });

      expect(onStartAgent).toHaveBeenCalledOnce();
    } finally {
      await act(async () => {
        resolveStart?.();
        await Promise.resolve();
      });
    }
  });

  it("reports a failed Sovereign Agent start as terminal runtime state", async () => {
    const props = {
      ...baseProps(),
      agentReady: true,
      agentJob: repoScopedJob({ status: 'completed' }),
      onStartAgent: vi.fn(async () => {
        throw new Error("Backend session missing");
      }),
    };
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();
    fireEvent.change(chatField(), { target: { value: "Implementiere den mobilen Chat-Fix als Draft PR." } });
    fireEvent.click(sendButton());
    const draftCard = await screen.findByTestId('integration-intent-draft-card');
    expect(props.onStartAgent).not.toHaveBeenCalled();
    fireEvent.click(within(draftCard).getByRole('button', { name: 'Repository-Auftrag starten' }));
    await waitFor(() => expect(props.onStartAgent).toHaveBeenCalledOnce());
    const actionStream = getActionStream();
    await waitFor(() =>
      expect(actionStream).toHaveTextContent("Sovereign Agent Start fehlgeschlagen"),
    );
    fireEvent.click(within(actionStream).getByRole("button", { name: "Details" }));
    expect(actionStream).toHaveTextContent("Backend session missing");
    await waitFor(() => expect(screen.getAllByText(/Start fehlgeschlagen: Backend session missing/i).length).toBeGreaterThan(0));
  });

  it("does not show Sovereign Agent as mandatory blocker when executor is not ready", async () => {
    const props = { ...baseProps(), agentReady: false };
    renderWithProviders(<BuilderContainer {...props} />);
    fireEvent.change(chatField(), { target: { value: "Implementiere den Chat-Fix als Draft PR." } });
    fireEvent.click(sendButton());
    // When GitHub write access is missing, Sovereign Agent is NOT shown as mandatory
    // Either GitHub access is required, or Sovereign Internal Operator is available
    await waitFor(() => {
      // The old blocker message "Sovereign Agent.*konfigurieren" should not appear
      expect(screen.queryByText(/Sovereign Agent.*konfigurieren/i)).toBeNull();
    });
  });


  it("SovereignToolLauncher github_access opens the secure GitHubAccessCard directly", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    fireEvent.click(screen.getByLabelText("GitHub Access"));

    await waitFor(() => expect(screen.getByText(/GitHub-Zugang fehlt/i)).toBeDefined());
    expect(screen.getByText("Zugang eingeben")).toBeDefined();
    expect(screen.queryByText(/Token im Kanal/i)).toBeNull();
  });

  it("closes a manually opened GitHub access surface without changing the access state", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Menü"));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Sovereign Seitenmenü" }))
      .getByRole("button", { name: /GitHub Access/i }));

    await waitFor(() => expect(screen.getByText(/GitHub-Zugang fehlt/i)).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: "GitHub-Zugang schließen" }));

    expect(screen.queryByText(/GitHub-Zugang fehlt/i)).toBeNull();
    expect(getActionStream())
      .toHaveTextContent("GitHub-Zugangsfläche geschlossen");
  });

  it("compact launcher trusts only a complete runtime repo snapshot, not the repoReady prop", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));

    const repoItem = screen.getByRole("menuitem", { name: "Repo" });
    const filesItem = screen.getByRole("menuitem", { name: "Files" });
    expect(repoItem).toHaveAttribute("data-gate-state", "setup_required");
    expect(repoItem.getAttribute("title")).toContain("Noch kein bestätigter Repo-Snapshot");
    expect(filesItem).not.toBeDisabled();
    expect(filesItem).toHaveAttribute("aria-disabled", "false");
    expect(filesItem).toHaveAttribute("data-can-open", "false");
  });

  it("blocked Diff shortcut records its runtime blocker and next action", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} />);
    await loadRepoFromChat();

    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    const diffItem = screen.getByRole("menuitem", { name: "Diff" });
    expect(diffItem).not.toBeDisabled();
    expect(diffItem).toHaveAttribute("aria-disabled", "false");
    expect(diffItem).toHaveAttribute("data-can-open", "false");
    fireEvent.click(diffItem);

    await waitFor(() => expect(screen.getAllByText(/Keine Changed-Files- oder Patch-Diff-Evidence vorhanden/i).length).toBeGreaterThan(0));
    const actionStream = getActionStream();
    expect(actionStream).toHaveTextContent("Diff blockiert");
    fireEvent.click(within(actionStream).getByRole("button", { name: "Details" }));
    expect(actionStream.querySelector('[data-route="diff"][data-state="blocked"]')).not.toBeNull();
  });

  it("active Executor shortcut shows the running job without requesting a duplicate start", async () => {
    const onStartAgent = vi.fn();
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        onStartAgent={onStartAgent}
        agentJob={repoScopedJob()}
      />,
    );
    await loadRepoFromChat();

    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    const executorItem = screen.getByRole("menuitem", { name: "Executor" });
    expect(executorItem).toHaveAttribute("data-gate-state", "inspection");
    expect(executorItem.getAttribute("title")).toContain("Job läuft");
    fireEvent.click(executorItem);

    expect(onStartAgent).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getAllByText(/bereits ein bestätigter Executor-Job aktiv/i).length).toBeGreaterThan(0));
    const actionStream = getActionStream();
    expect(actionStream).toHaveTextContent("Laufender Executor-Job angezeigt");
    fireEvent.click(within(actionStream).getByRole("button", { name: "Details" }));
    expect(actionStream.querySelector('[data-route="agent-job"][data-state="running"]')).not.toBeNull();
  });

  it("Repo shortcut opens a real setup surface and closes it with Escape", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Repo" }));

    expect(screen.getByRole("dialog", { name: "Repo Setup" })).toBeDefined();
    const repoUrlInput = screen.getByLabelText("GitHub Repository URL");
    expect(repoUrlInput).toBeDefined();
    expect(screen.queryByRole("dialog", { name: "Repo Inspector" })).toBeNull();
    expect(getActionStream()).toHaveTextContent("Repo-Setup geöffnet");

    fireEvent.keyDown(repoUrlInput, { key: "Escape", code: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Repo Setup" })).toBeNull();
  });

  it("Files shortcut preserves its own intent and opens the confirmed file explorer", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} />);
    fireEvent.change(chatField(), { target: { value: "https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByLabelText('Repo Inspector öffnen')).toBeDefined());

    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    const filesItem = screen.getByRole("menuitem", { name: "Files" });
    expect(filesItem).toHaveAttribute("data-gate-state", "ready");
    fireEvent.click(filesItem);

    expect(screen.getByRole("dialog", { name: "Repo Inspector" })).toBeDefined();
    const actionStream = getActionStream();
    expect(actionStream).toHaveTextContent("Datei-Explorer geöffnet");
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(actionStream.querySelector('[data-route="files"]')).not.toBeNull();
  });

  it("Diff shortcut opens changed-file evidence only for the loaded repo job", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob({ runtimeId: "conv_diff", changedFiles: ["src/App.tsx"] })}
      />,
    );
    await loadRepoFromChat();
    const before = chatField().value;
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Diff" }));

    expect(screen.getAllByText("Changed").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("src/App.tsx")).toBeDefined();
    const actionStream = getActionStream();
    expect(actionStream).toHaveTextContent("Diff-Prüfung geöffnet");
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(actionStream.querySelector('[data-route="diff"]')).not.toBeNull();
    expect(chatField().value).toBe(before);
  });

  it("Health shortcut closes its running route only after real inspection evidence is stored", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Health" }));

    const actionStream = getActionStream();
    await waitFor(() => expect(actionStream).toHaveTextContent("health Inspektion abgeschlossen"));
    fireEvent.click(within(actionStream).getByRole("button", { name: "Details" }));

    const result = actionStream.querySelector('[data-route="health"]:not([data-state="running"])');
    expect(result).not.toBeNull();
    expect(useSovereignToolInspectionStore.getState().evidence.health).toBeTruthy();
  });

  it("Runtime Logs shortcut is idempotent and never creates its own evidence", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    const emptyLogsItem = screen.getByRole("menuitem", { name: "Runtime Logs" });
    expect(emptyLogsItem.getAttribute("title")).toContain("Noch leer");
    fireEvent.click(emptyLogsItem);

    expect(screen.getByRole("dialog", { name: "Runtime Evidence Logs" })).toBeDefined();
    expect(screen.getByText(/Keine Tabwechsel- oder UI-Signallogs/i)).toBeDefined();
    expect(screen.getByText("Noch keine Runtime-Ereignisse.")).toBeDefined();
    fireEvent.click(screen.getByLabelText("Runtime Logs schließen"));

    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    const logsItemAfterOpen = screen.getByRole("menuitem", { name: "Runtime Logs" });
    expect(logsItemAfterOpen.getAttribute("title")).toContain("Noch leer");
    fireEvent.click(logsItemAfterOpen);
    expect(screen.getByText("Noch keine Runtime-Ereignisse.")).toBeDefined();
  });

  it("rejects foreign Sovereign Agent evidence for the loaded repository", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob({
          repoUrl: SECOND_REPO_URL,
          changedFiles: ["src/Foreign.tsx"],
          draftPrUrl: "https://github.com/OuroborosCollective/Other-Studio/pull/1",
        })}
      />,
    );
    await loadRepoFromChat();

    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    const diffItem = screen.getByRole("menuitem", { name: "Diff" });
    expect(diffItem).not.toBeDisabled();
    expect(diffItem).toHaveAttribute("aria-disabled", "false");
    expect(diffItem).toHaveAttribute("data-can-open", "false");
    expect(diffItem.getAttribute("title")).toContain("Kein Diff");
    expect(screen.queryByText("src/Foreign.tsx")).toBeNull();
    expect(screen.queryByText(/Draft PR öffnen/i)).toBeNull();
  });

  it("hides job-bound monitor observations when the loaded repository differs", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob({ repoUrl: SECOND_REPO_URL })}
        agentProjections={[repoScopedProjection()]}
        agentEvidenceAnchors={[repoScopedEvidenceAnchor()]}
        desktopFrame={{
          jobId: "job_scoped",
          url: "blob:foreign-repository-frame",
          frameHash: "9".repeat(64),
          observedAt: 1,
        }}
      />,
    );
    await loadRepoFromChat();

    expect(screen.queryByAltText("Beobachteter Sovereign Workspace Desktop")).toBeNull();
    expect(screen.queryByText("monitor runtime output")).toBeNull();
    expect(screen.queryByTestId("workspace-evidence-rail")).toBeNull();
    expect(screen.getByTestId("live-workspace-monitor-desktop-unavailable")).toBeDefined();
  });

  it("hides an evidence anchor from another job in the loaded repository", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob()}
        agentEvidenceAnchors={[repoScopedEvidenceAnchor({ jobId: 'job-other' })]}
      />,
    );
    await loadRepoFromChat();

    expect(screen.queryByTestId("workspace-evidence-rail")).toBeNull();
  });

  it("rejects a published Draft PR URL from another repository", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        publishedPrUrl="https://github.com/OuroborosCollective/Other-Studio/pull/99"
      />,
    );
    await loadRepoFromChat();
    fireEvent.click(screen.getByText('INSPECTOR'));

    expect(screen.queryByRole("button", { name: "Draft PR öffnen" })).toBeNull();
    const draftStatus = screen.getByRole("button", { name: /Draft PR:/i });
    expect(draftStatus).toHaveTextContent("fehlt");
  });

  it("invalidates validated GitHub access when another repository is loaded", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
      jsonResponse({ tree: [{ path: "src/Other.tsx", type: "blob", size: 21 }], truncated: false }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} agentJob={repoScopedJob({ status: 'completed' })} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();

    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    expect(screen.getByRole("menuitem", { name: "GitHub Access" }).getAttribute("title")).toContain("Validiert");
    fireEvent.click(screen.getByLabelText("Tool Launcher schließen"));

    await loadRepoUrlFromChat(SECOND_REPO_URL);
    const actionStream = getActionStream();
    expect(actionStream).not.toHaveTextContent("GitHub-Zugang bereit");
    expect(actionStream).toHaveTextContent("Repo-Kontext geladen");
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    const accessItem = screen.getByRole("menuitem", { name: "GitHub Access" });
    expect(accessItem.getAttribute("title")).toContain("Zugang fehlt");
    expect(accessItem.getAttribute("title")).not.toContain("Validiert");
  });

  it("discards a GitHub validation result that finishes after the repo scope changed", async () => {
    let resolveValidation: ((response: Response) => void) | null = null;
    const pendingValidation = new Promise<Response>((resolve) => { resolveValidation = resolve; });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (isAuthBootstrapRequest(input)) return authBootstrapResponse();
      const url = requestUrl(input);
      if (url.includes('/api/user/agent/github-access/scope')) {
        return jsonResponse({ ok: true, scope: 'v1.test-scope.signature' });
      }
      if (url.includes('/api/user/agent/github-access/validate')) return pendingValidation;
      if (url.includes('/git/trees/')) {
        return jsonResponse({ sha: 'a'.repeat(40), tree: [{ path: url.includes('Other-Studio') ? 'src/Other.tsx' : 'README.md', type: 'blob', size: 12 }], truncated: false });
      }
      if (url.includes('/commits/')) return jsonResponse({ sha: 'c'.repeat(40) });
      return runtimeSupportResponse(url, init)
        ?? jsonResponse({ choices: [{ message: { content: 'unused' } }] });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} agentJob={repoScopedJob({ status: 'completed' })} />);
    await loadRepoFromChat();
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    fireEvent.click(screen.getByLabelText('GitHub Access'));
    fireEvent.click(screen.getByText('Zugang eingeben'));
    fireEvent.change(screen.getByLabelText(/GitHub Token/i), { target: { value: fakeGitHubPat() } });
    fireEvent.click(screen.getByText('Übernehmen'));
    await waitFor(() =>
      expect(getActionStream()).toHaveTextContent('GitHub-Zugang wird geprüft'),
    );

    await loadRepoUrlFromChat(SECOND_REPO_URL);
    resolveValidation?.(jsonResponse({ ok: true, canWrite: true, code: 'ready', error: null }));

    await waitFor(() =>
      expect(getActionStream()).toHaveTextContent('GitHub-Zugangsprüfung verworfen'),
    );
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    expect(screen.getByRole('menuitem', { name: 'GitHub Access' }).getAttribute('title')).toContain('Zugang fehlt');
  });

  it("ignores a stale OAuth failure after a newer manual PAT validation succeeds for the same repo", async () => {
    let resolveOAuthValidation: ((response: Response) => void) | null = null;
    const pendingOAuthValidation = new Promise<Response>((resolve) => {
      resolveOAuthValidation = resolve;
    });
    let validationCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (isAuthBootstrapRequest(input)) return authBootstrapResponse();
      const url = requestUrl(input);
      if (url.includes('/api/user/agent/github-access/scope')) {
        return jsonResponse({ ok: true, scope: 'v1.test-scope.signature' });
      }
      if (url.includes('/api/user/agent/github-access/validate')) {
        validationCalls += 1;
        const body = requestJsonBody(init);
        if (typeof body.githubAccessToken === 'string') {
          return jsonResponse({ ok: true, canWrite: true, code: 'ready', error: null });
        }
        return pendingOAuthValidation;
      }
      if (url.includes('/git/trees/')) {
        return jsonResponse({ sha: 'a'.repeat(40), tree: [{ path: 'README.md', type: 'blob', size: 12 }], truncated: false });
      }
      if (url.includes('/commits/')) return jsonResponse({ sha: 'c'.repeat(40) });
      return runtimeSupportResponse(url, init)
        ?? jsonResponse({ choices: [{ message: { content: 'unused' } }] });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} agentJob={repoScopedJob({ status: 'completed' })} />);
    await loadRepoFromChat();
    useUserStore.setState({ user: { ...TEST_AUTH_USER, githubId: 'oauth-user-123' } });
    await waitFor(() => expect(validationCalls).toBe(1));

    await validateGitHubAccessFromLauncher();
    expect(validationCalls).toBe(2);
    resolveOAuthValidation?.(jsonResponse({ ok: false, canWrite: false, code: 'temporary_error', error: 'stale OAuth failure' }, 503));
    await act(async () => { await Promise.resolve(); });

    const actionStream = getActionStream();
    expect(actionStream).toHaveTextContent('GitHub-Zugang bereit');
    expect(actionStream).not.toHaveTextContent('GitHub OAuth reicht für dieses Repo nicht aus');
    await new Promise((resolve) => window.setTimeout(resolve, 850));
    expect(validationCalls).toBe(2);
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    expect(screen.getByRole('menuitem', { name: 'GitHub Access' }).getAttribute('title')).toContain('Validiert');
  });

  it("serializes rapid duplicate preset submits before React busy state is visible", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} agentReady={false} />);
    const callsBeforePreset = nonAuthFetchCalls(fetchMock).length;
    const presetButton = screen.getByRole("button", { name: /Fehler suchen & als Draft PR reparieren/i });
    await waitFor(() => expect(presetButton).not.toBeDisabled());

    fireEvent.click(presetButton);
    fireEvent.click(presetButton);

    await waitFor(() => expect(screen.getByRole("dialog", { name: "Repo Setup" })).toBeDefined());
    const actionStream = getActionStream();
    expect(actionStream.textContent?.match(/Preset wartet auf Repo: Fehler/g) ?? []).toHaveLength(1);
    expect(screen.queryByText(/Ich habe diesen Auftrag vorgemerkt/i)).toBeNull();
    expect(nonAuthFetchCalls(fetchMock)).toHaveLength(callsBeforePreset);
  });

  it("error repair preset opens the secure GitHub gate instead of falling back to read-only advice", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} agentReady={false} />);
    const callsBeforePreset = nonAuthFetchCalls(fetchMock).length;
    const presetButton = screen.getByRole("button", { name: /Fehler suchen & als Draft PR reparieren/i });
    await waitFor(() => expect(presetButton).not.toBeDisabled());

    fireEvent.click(presetButton);
    await waitFor(() => expect(screen.getByRole("dialog", { name: "Repo Setup" })).toBeDefined());
    fireEvent.change(screen.getByLabelText("GitHub Repository URL"), { target: { value: TEST_REPO_URL } });
    fireEvent.click(screen.getByRole("button", { name: "Repo-Snapshot laden" }));

    await waitFor(() => expect(screen.getByText(/GitHub-Zugang fehlt/i)).toBeDefined());
    expect(nonAuthFetchCalls(fetchMock).length).toBeGreaterThan(callsBeforePreset);
    expect(getActionStream())
      .not.toHaveTextContent("Code-Auftrag braucht Ergebnis-Gate");
    expect(screen.queryByText(/Was ist die sichere Analyse für dieses Repo/i)).toBeNull();
  });

  it("README & Docs preset opens real repo setup before GitHub access when repo evidence is missing", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} agentReady={false} />);
    fireEvent.click(screen.getByRole("button", { name: /README & Docs aktualisieren/i }));

    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: "Repo Setup" })).toBeDefined(),
    );
    expect(screen.getByLabelText("GitHub Repository URL")).toBeDefined();
    expect(getActionStream())
      .toHaveTextContent("Preset wartet auf Repo: Docs");
    expect(screen.queryByText("Zugang eingeben")).toBeNull();
  });

  it("uses the configured Sovereign Agent API for the GitHub scope preflight", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentConfig={{
          enabled: true,
          deploymentMode: 'sovereign-agent-backend',
          agentApiUrl: 'https://agent.example.test',
          ready: true,
          reason: 'test agent backend',
        }}
      />,
    );
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();

    const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
    expect(calls).toContain('https://agent.example.test/api/user/agent/github-access/scope');
    expect(calls).toContain('https://agent.example.test/api/user/agent/github-access/validate');
  });

  it("keeps a valid Draft-PR order in review when no product executor is connected", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );

    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} agentReady={false} agentJob={repoScopedJob({ status: 'completed' })} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();

    fireEvent.change(chatField(), { target: { value: "Erstelle einen Draft PR für README und Docs." } });
    fireEvent.click(sendButton());

    const draftCard = await screen.findByTestId('integration-intent-draft-card');
    expect(within(draftCard).getByTestId('confirm-blocker'))
      .toHaveTextContent('Backend-Workspace-Executor ist nicht verbunden.');
    expect(within(draftCard).getByRole('button', { name: 'Repository-Auftrag starten' })).toBeDisabled();
    expect(getActionStream())
      .not.toHaveTextContent("Freigegebener Repository-Auftrag angefragt");
    expect(nonAuthFetchCalls(fetchMock).length).toBeGreaterThanOrEqual(3);
  });

  it("retries a transient server-held OAuth validation once for the same mounted repository", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ ok: false, canWrite: false, code: 'temporary_error', error: 'temporary backend outage' }, 503),
      jsonResponse({ ok: true, canWrite: true, code: 'ready', error: null }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} />);
    await loadRepoFromChat();

    useUserStore.setState({ user: { ...TEST_AUTH_USER, githubId: 'oauth-user-123' } });

    const oauthValidationCalls = () => fetchMock.mock.calls.filter(([input]) => (
      requestUrl(input as RequestInfo | URL).includes('/api/user/agent/github-access/validate')
    ));
    await waitFor(() => expect(oauthValidationCalls()).toHaveLength(1));
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    expect(oauthValidationCalls()).toHaveLength(1);
    await waitFor(() => expect(oauthValidationCalls()).toHaveLength(2), { timeout: 2500 });
    await waitFor(() => expect(
      getActionStream(),
    ).toHaveTextContent('GitHub-Zugang bereit'));
    expect(screen.queryByLabelText(/GitHub Token/i)).toBeNull();

    await new Promise((resolve) => window.setTimeout(resolve, 850));
    expect(oauthValidationCalls()).toHaveLength(2);
  });

  it("routes the exact degraded /direct-patch command to the supported executor and stops at GitHub consent", async () => {
    const onStartAgent = vi.fn();
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: 'docs/README.md', type: 'blob', size: 42 }], truncated: false }),
      jsonResponse({ error: { message: 'language provider unavailable', type: 'upstream_error' } }, 503),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob({ status: 'completed' })}
        onStartAgent={onStartAgent}
      />,
    );
    await loadRepoFromChat();

    fireEvent.change(chatField(), {
      target: { value: '/direct-patch ändere docs/README.md, prüfe den Test und erzeuge nur einen Draft PR' },
    });
    fireEvent.click(sendButton());

    const actionStream = getActionStream();
    await waitFor(() => expect(actionStream).toHaveTextContent('Executor braucht GitHub-Zugang'));
    expect(actionStream).not.toHaveTextContent('Kein bestätigter Code- oder Draft-PR-Ausführungsauftrag');
    expect(onStartAgent).not.toHaveBeenCalled();
    expect(screen.queryByTestId('integration-intent-draft-card')).toBeNull();
    expect(fetchMock.mock.calls.some(([input]) => (
      requestUrl(input as RequestInfo | URL).includes('/api/llm/chat')
    ))).toBe(true);
  });

  it("never routes ordinary free language to GitHub or the executor when the online LLM is unavailable", async () => {
    const onStartAgent = vi.fn();
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ error: { message: "language provider unavailable", type: "upstream_error" } }, 503),
    );
    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob({ status: 'completed' })}
        onStartAgent={onStartAgent}
      />,
    );
    await loadRepoFromChat();

    fireEvent.change(chatField(), { target: { value: 'Implementiere bitte die README neu und repariere den Text.' } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(
      getActionStream(),
    ).toHaveTextContent('Codeauftragsvertrag blockiert'));
    await waitFor(() => expect(
      screen.getAllByText('Die sichere Online-Aktionsroute ist blockiert. Soll ich denselben Auftrag mit Auto/Revolver erneut versuchen?').length,
    ).toBeGreaterThan(0));
    expect(onStartAgent).not.toHaveBeenCalled();
    expect(screen.queryByText(/GitHub-Zugang fehlt/i)).toBeNull();
    expect(screen.queryByTestId('integration-intent-draft-card')).toBeNull();
    expect(getActionStream())
      .not.toHaveTextContent('Sovereign Agent Job angefragt');
    expect(fetchMock.mock.calls.some(([input]) => requestUrl(input as RequestInfo | URL).includes('/api/llm/chat'))).toBe(true);
  });

  it("rejects unrelated provider prose and never wakes a pending write intent", async () => {
    const onStartAgent = vi.fn();
    const rawProviderText = 'Die LICENSE beschreibt die Nutzungsbedingungen des Repositorys.';
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (isAuthBootstrapRequest(input)) return authBootstrapResponse();
      if (url.includes('/api/llm/routes')) return liteLlmRouteCatalogResponse();
      if (url.includes('/git/trees/')) {
        return jsonResponse({ sha: 'a'.repeat(40), tree: [{ path: 'LICENSE', type: 'blob', size: 1100 }] });
      }
      if (url.includes('/commits/')) return jsonResponse({ sha: 'c'.repeat(40) });
      if (url.includes('/api/llm/chat')) {
        return jsonResponse({
          model: TEST_LITELLM_MODEL,
          choices: [{ message: { content: rawProviderText } }],
        });
      }
      return runtimeSupportResponse(url, init) ?? jsonResponse({ ok: true });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithProviders(
      <BuilderContainer
        {...baseProps()}
        mission=""
        repoReady={false}
        agentReady
        agentJob={repoScopedJob({ status: 'completed' })}
        onStartAgent={onStartAgent}
      />,
    );
    await loadRepoFromChat();

    fireEvent.change(chatField(), { target: { value: 'Erkläre mir LICENSE und was dort geregelt ist.' } });
    fireEvent.click(sendButton());

    const actionStream = getActionStream();
    await waitFor(() => expect(actionStream).toHaveTextContent('Codeauftragsvertrag blockiert'));
    expect(screen.queryByText(rawProviderText)).toBeNull();
    expect(onStartAgent).not.toHaveBeenCalled();
    expect(screen.queryByTestId('integration-intent-draft-card')).toBeNull();
    expect(actionStream).not.toHaveTextContent('Freitext-Antwort ohne Aktionsschema übernommen');
  });


  it("does not claim that a newly created empty PostgreSQL session was restored", async () => {
    testChatSession = {
      ...testChatSession,
      recordedAt: new Date().toISOString(),
    };
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }] }),
    );

    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} />);
    await loadRepoFromChat();
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      requestUrl(input as RequestInfo | URL).endsWith("/bubbles")
    ))).toBe(true));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.queryByText(/Session erfolgreich wiederhergestellt/i)).toBeNull();
    expect(screen.queryByText(/wiederhergestellte Session ist älter/i)).toBeNull();
  });

  it("retains the restoration notice when hydration completes outside the monitor tab", async () => {
    let resolveRepository: ((response: Response) => void) | null = null;
    const repositoryResponse = new Promise<Response>((resolve) => {
      resolveRepository = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (isAuthBootstrapRequest(input)) return authBootstrapResponse();
      const url = requestUrl(input);
      if (isToolchainBootstrapRequest(input)) {
        return runtimeSupportResponse(url, init) ?? jsonResponse({ ok: true });
      }
      if (url.includes("/api/llm/routes")) return liteLlmRouteCatalogResponse();
      if (isGitHubApiRequest(input)) {
        if (url.includes("/commits/")) return jsonResponse({ sha: "c".repeat(40) });
        return repositoryResponse;
      }
      if (url.endsWith("/bubbles")) {
        return jsonResponse({
          session: testChatSession,
          bubbles: [testMissionBubble({
            body: JSON.stringify({
              text: "Wiederhergestellte Mission",
              clientMessageId: "restored-mission",
            }),
          })],
        });
      }
      return runtimeSupportResponse(url, init) ?? jsonResponse({ ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} />);
    fireEvent.change(chatField(), { target: { value: TEST_REPO_URL } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      isGitHubApiRequest(input as RequestInfo | URL)
      && !requestUrl(input as RequestInfo | URL).includes("/commits/")
    ))).toBe(true));

    fireEvent.click(screen.getByText("INSPECTOR"));
    fireEvent.click(screen.getByLabelText("init"));
    expect(screen.getByTestId("builder-container")).toHaveAttribute(
      "data-layout",
      "chat-inspector-modules",
    );

    await act(async () => {
      resolveRepository?.(jsonResponse({
        sha: "c".repeat(40),
        tree: [{ path: "src/App.tsx", type: "blob", size: 42 }],
      }));
      await repositoryResponse;
    });
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      requestUrl(input as RequestInfo | URL).endsWith("/bubbles")
    ))).toBe(true));

    fireEvent.click(screen.getByRole("button", { name: "Sovereign Chat" }));
    expect(await screen.findByText(/wiederhergestellte Session ist älter als 3 Tage/i)).toBeDefined();
  });
});
