import React from "react";
import { Provider } from "react-redux";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BuilderContainer } from "./BuilderContainer";
import { useUserStore } from "../../user/useUserStore";
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
  return screen.getByLabelText(/Sovereign Chat Eingabe/i) as HTMLTextAreaElement;
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

function isAuthBootstrapRequest(input: RequestInfo | URL): boolean {
  return requestUrl(input).includes("/api/auth/me");
}

function authBootstrapResponse(): Response {
  return jsonResponse({ error: "not authenticated" }, 401);
}

function mockFetchSequence(...responses: Array<Response | (() => Response | Promise<Response>)>) {
  const queue = [...responses];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    if (isAuthBootstrapRequest(input)) return authBootstrapResponse();
    const next = queue.shift();
    if (!next) return jsonResponse({ choices: [{ message: { content: "Worker Antwort aus Cloudflare Route." } }] });
    return typeof next === "function" ? next() : next;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function nonAuthFetchCalls(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.filter(([input]) => !isAuthBootstrapRequest(input as RequestInfo | URL));
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

const TEST_REPO_URL = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato';
const SECOND_REPO_URL = 'https://github.com/OuroborosCollective/Other-Studio';

function repoScopedJob(overrides: Record<string, unknown> = {}) {
  return {
    status: 'running' as const,
    repoUrl: TEST_REPO_URL,
    branch: 'main',
    runtimeId: 'conv_scoped',
    changedFiles: [] as string[],
    events: [],
    ...overrides,
  };
}

async function loadRepoUrlFromChat(repoUrl: string): Promise<void> {
  fireEvent.change(chatField(), { target: { value: repoUrl } });
  fireEvent.click(sendButton());
  await waitFor(() => expect(screen.getAllByText(/Repo geladen/).length).toBeGreaterThan(0));
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
  await waitFor(() => expect(screen.getByText(/GitHub-Zugang ist bereit/i)).toBeDefined());
}

beforeEach(() => {
  window.localStorage.clear();
  useUserStore.getState().clearUser();
  mockWorkerReply();
});

afterEach(() => {
  useUserStore.getState().clearUser();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("BuilderContainer (AppControl DevChat shell)", () => {
  it("renders the AppControl DevChat shell structure", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    const root = screen.getByTestId("builder-container");
    expect(root).toHaveAttribute("data-layout", "devchat-appcontrol-integrated");
    expect(root).toHaveAttribute("aria-label", "Sovereign Builder");
    expect(screen.getAllByText("Sovereign").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("DevChat")).toBeDefined();
    expect(screen.getByLabelText("Sovereign Studio Tabs")).toBeDefined();
    expect(screen.getByText("CHAT")).toBeDefined();
    expect(screen.getByText("INSPECTOR")).toBeDefined();
    expect(screen.getByTestId("sovereign-chat-body-window")).toBeDefined();
    expect(chatField()).toBeDefined();
    expect(screen.getByLabelText("Menü")).toBeDefined();
  });

  it("shows the Workbench status vocabulary (Actions/Files/Logs/Errors/Draft PR) as primary nav, not technical module abbreviations", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    expect(screen.getByLabelText("Werkbank Status")).toBeDefined();
    expect(screen.getByRole("button", { name: /^Actions:/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^Changed:/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^Logs:/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^Errors:/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^Draft PR:/ })).toBeDefined();
    expect(screen.queryByText("ROU")).toBeNull();
    expect(screen.queryByText("INT")).toBeNull();
    expect(screen.queryByText("PAT")).toBeNull();
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
    fireEvent.click(screen.getByRole("button", { name: /^Changed:/ }));
    expect(screen.getByText("src/App.tsx")).toBeDefined();
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
    expect(screen.queryByText("Terminal")).toBeNull();
    expect(screen.queryByText(/Sovereign geführter Chat Ablauf/i)).toBeNull();
  });

  it("keeps DevChat content as runtime-derived messages, not demo flow", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    expect(screen.getAllByText(/Repo fehlt/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Bitte mobile UX verbessern und Log direkt sichtbar machen.").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Package summary")).toBeDefined();
    expect(screen.queryByText(/AutoSwitchOrchestrator/)).toBeNull();
    expect(screen.queryByText(/simulate/i)).toBeNull();
  });

  it("shows suggestions only in empty chat state and writes them into the input", () => {
    const props = baseProps();
    renderWithProviders(<BuilderContainer {...props} mission="" />);
    expect(screen.getByText("Let's build!")).toBeDefined();
    fireEvent.click(screen.getByText("🔒 Runtime"));
    expect(chatField().value).toContain("Prüfe den schwächsten Ablauf");
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it("shows integration intent draft card for normal text inputs when repo is ready", async () => {
    const props = baseProps();
    mockFetchSequence(jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} agentReady={false} />);
    await loadRepoFromChat();
    fireEvent.change(chatField(), { target: { value: "Bitte mobile UX verbessern und Log direkt sichtbar machen." } });
    expect(sendButton()).not.toBeDisabled();
    fireEvent.click(sendButton());
    expect(chatField().value).toBe("");
    // Issue #520: Normal text with repo loaded shows draft card instead of routing to Worker
    await waitFor(() => expect(screen.getByTestId("integration-intent-draft-card")).toBeInTheDocument());
    // Draft card should show the title
    expect(screen.getByText(/Ich habe daraus diesen Integrationsauftrag erkannt/)).toBeInTheDocument();
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

  it("does not duplicate an already analysed mission when Sovereign Agent execution is requested", async () => {
    const props = { ...baseProps(), agentReady: true, onStartAgent: vi.fn() };
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();
    fireEvent.change(chatField(), { target: { value: "Bitte Sovereign Agent: implementiere den mobilen Chat-Fix als Draft PR." } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(props.onMissionChange).toHaveBeenCalled());
    const emittedMission = props.onMissionChange.mock.calls[0][0] as string;
    expect(emittedMission.match(/Ideenfabrik Auftrag:/g)).toHaveLength(1);
    expect(emittedMission.match(/Repository-Kontext:/g)).toHaveLength(1);
    expect(emittedMission).toContain("implementiere den mobilen Chat-Fix");
    await waitFor(() => expect(props.onStartAgent).toHaveBeenCalledOnce());
  });

  it("opens the DevChat side menu as overlay without changing the shell structure", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    expect(screen.queryByText("Sovereign Studio")).toBeNull();
    fireEvent.click(screen.getByLabelText("Menü"));
    expect(screen.getByText("Sovereign Studio")).toBeDefined();
    expect(screen.getByText(/Cloudflare Workers/i)).toBeDefined();
    expect(screen.getByRole("dialog", { name: "Sovereign Seitenmenü" })).toBeDefined();
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

  it("side menu analysis actions use the real repo gate instead of legacy direct callbacks", () => {
    const props = baseProps();
    renderWithProviders(<BuilderContainer {...props} />);
    fireEvent.click(screen.getByLabelText("Menü"));
    const sideMenu = screen.getByRole("dialog", { name: "Sovereign Seitenmenü" });

    fireEvent.click(within(sideMenu).getByRole("button", { name: "Auftrag analysieren" }));

    expect(screen.getByRole("dialog", { name: "Repo Setup" })).toBeDefined();
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
    expect(screen.getByText(/Das echte Repo-Setup wurde geöffnet/i)).toBeDefined();
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

  it("side menu disables Draft PR when a repo exists but no change evidence exists", async () => {
    const props = baseProps();
    mockFetchSequence(jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();

    fireEvent.click(screen.getByLabelText("Menü"));
    const draftButton = within(screen.getByRole("dialog", { name: "Sovereign Seitenmenü" }))
      .getByTestId("builder__draft-pr");
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
    const actionStream = screen.getByRole("log", { name: "Sovereign Action Stream" });
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

    expect(props.onPublishDraftPr).toHaveBeenCalledOnce();
    expect(screen.getByRole("log", { name: "Sovereign Action Stream" })).toHaveTextContent("Draft-PR-Publisher aufgerufen");
  });

  it("opens runtime source sheet with Cloudflare Worker as the standard LLM route", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} agentReady onStartAgent={vi.fn()} />);
    const rtButton = screen.getByRole("button", { name: /RT.*Runtime Quelle/i });
    expect(rtButton).toHaveAttribute("title", "Runtime Quelle");
    fireEvent.click(rtButton);
    expect(screen.getByText("Runtime Quelle")).toBeDefined();
    expect(screen.getByText("Cloudflare Worker")).toBeDefined();
    expect(screen.getByText("Interne Sovereign Agent Runtime für Code/Draft-PR-Aufträge")).toBeDefined();
  });

  it("starts the external agent only for explicit code or Draft-PR execution intent", async () => {
    const props = { ...baseProps(), agentReady: true, onStartAgent: vi.fn() };
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();
    fireEvent.change(chatField(), { target: { value: "Bitte implementiere einen Chat-State-Fix als Draft PR." } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(props.onStartAgent).toHaveBeenCalledOnce());
    expect(props.onStartAgent.mock.calls[0][0]).toContain("Ideenfabrik Auftrag");
    expect(props.onStartAgent.mock.calls[0][1]).toEqual({ repoUrl: TEST_REPO_URL, branch: "main" });
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
  });

  it("shows repo status when not ready but does not block normal chat", async () => {
    const props = baseProps();
    renderWithProviders(<BuilderContainer {...props} repoReady={false} agentReady />);
    expect(screen.getAllByText(/Repo fehlt/).length).toBeGreaterThanOrEqual(1);
    expect(sendButton()).not.toBeDisabled();
    fireEvent.change(chatField(), { target: { value: "Was brauchst du als nächstes?" } });
    fireEvent.click(sendButton());
    expect(chatField().value).toBe("");
    await waitFor(() => expect(screen.getByText("Worker Antwort aus Cloudflare Route.")).toBeDefined());
    expect(props.onMissionChange).not.toHaveBeenCalled();
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
    await waitFor(() => expect(screen.getByText(/Repo geladen/)).toBeDefined());
    expect(screen.getAllByText(repoUrl).length).toBeGreaterThanOrEqual(1);
    expect(chatField().value).not.toContain("Repo geladen");
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it("routes normal text after repo load through Cloudflare Worker instead of Sovereign Agent", async () => {
    const props = { ...baseProps(), agentReady: true, onStartAgent: vi.fn() };
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 123 }], truncated: false }),
      jsonResponse({ choices: [{ message: { content: "Repo-Frage über Worker beantwortet." } }] }),
    );
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    fireEvent.change(chatField(), { target: { value: "https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByText(/Repo geladen/)).toBeDefined());
    fireEvent.change(chatField(), { target: { value: "Was ist der nächste sinnvolle Schritt?" } });
    fireEvent.click(sendButton());
    expect(chatField().value).toBe("");
    await waitFor(() => expect(screen.getByText("Repo-Frage über Worker beantwortet.")).toBeDefined());
    expect(props.onStartAgent).not.toHaveBeenCalled();
    expect(nonAuthFetchCalls(fetchMock)).toHaveLength(2);
  });

  it("shows streaming chunks in real-time and freezes final text after stream ends", async () => {
    mockFetchSequence(() => new Response([
      'data: {"choices":[{"delta":{"content":"Erste "}}]}',
      'data: {"choices":[{"delta":{"content":"Antwort"}}]}',
      "data: [DONE]",
    ].join("\n"), { status: 200, headers: { "Content-Type": "text/event-stream" } }));
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.change(chatField(), { target: { value: "Wie geht es dir?" } });
    fireEvent.click(sendButton());
    expect(screen.getAllByText("Wie geht es dir?").length).toBeGreaterThanOrEqual(1);
    await waitFor(() => expect(screen.getByText("Erste Antwort")).toBeDefined());
  });

  it("turns Worker HTTP 500 into a local runtime diagnostic and avoids blind repeat calls", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ error: { message: "Gateway exploded", type: "server_error" } }, 500),
      jsonResponse({ ok: true, provider: "sovereign-llm-bridge", gateway: "gatter", model: "cerebras/zai-glm-4.7", upstreamConfigured: true, secretConfigured: true }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} repoReady agentReady />);
    fireEvent.change(chatField(), { target: { value: "Hast du Vorschläge für bessere UI?" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByText(/Ich wiederhole den kaputten Worker-Call nicht blind/i)).toBeDefined());
    expect(screen.getAllByText(/HTTP 500/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/secret=ok/i).length).toBeGreaterThanOrEqual(1);
    fireEvent.change(chatField(), { target: { value: "Warum?" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getAllByText(/Ich wiederhole den kaputten Worker-Call nicht blind/i).length).toBeGreaterThanOrEqual(2));
    expect(nonAuthFetchCalls(fetchMock)).toHaveLength(2);
  });

  it("retries the original Worker request after a diagnostic follow-up", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ error: { message: "Gateway exploded", type: "server_error" } }, 500),
      jsonResponse({
        ok: true,
        provider: "sovereign-llm-bridge",
        gateway: "gatter",
        model: "cerebras/zai-glm-4.7",
        upstreamConfigured: true,
        secretConfigured: true,
      }),
      jsonResponse({ choices: [{ message: { content: "Retry beantwortet." } }] }),
    );

    renderWithProviders(<BuilderContainer {...baseProps()} repoReady agentReady />);

    fireEvent.change(chatField(), {
      target: { value: "Hast du Vorschläge für bessere UI?" },
    });
    fireEvent.click(sendButton());

    await waitFor(() =>
      expect(
        screen.getByText(/Ich wiederhole den kaputten Worker-Call nicht blind/i),
      ).toBeDefined(),
    );

    fireEvent.change(chatField(), { target: { value: "Warum?" } });
    fireEvent.click(sendButton());

    await waitFor(() =>
      expect(
        screen.getAllByText(/Ich wiederhole den kaputten Worker-Call nicht blind/i).length,
      ).toBeGreaterThanOrEqual(2),
    );

    fireEvent.click(screen.getAllByText("Retry")[0]);

    await waitFor(() => expect(screen.getByText("Retry beantwortet.")).toBeDefined());
    expect(screen.queryByText(/Sovereign Agent für Code-Auftrag/i)).toBeNull();
    expect(nonAuthFetchCalls(fetchMock)).toHaveLength(3);
    const actionStream = screen.getByRole("log", { name: "Sovereign Action Stream" });
    fireEvent.click(within(actionStream).getByRole("button", { name: "Details" }));
    const retryEvent = Array.from(actionStream.querySelectorAll('[data-route="runtime"]'))
      .find((node) => node.textContent?.includes("Retry gestartet"));
    expect(retryEvent).toHaveAttribute("data-state", "done");
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
    expect(screen.getAllByTitle("läuft").length).toBeGreaterThan(0);
    expect(screen.getByText(/1 Datei/)).toBeDefined();
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
    await waitFor(() => expect(screen.getByText(/Repo geladen/)).toBeDefined());
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
    await waitFor(() => expect(screen.getByText(/Repo geladen/)).toBeDefined());
    fireEvent.click(screen.getByLabelText("Repo Inspector öffnen"));
    const dialog = screen.getByTestId("repo-tree-explorer");
    expect(dialog).toBeDefined();
    fireEvent.click(within(dialog).getByText("App.tsx"));
    expect(chatField().value).toContain("Erkläre mir src/App.tsx");
    expect(props.onMissionChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId("repo-tree-explorer")).toBeNull();
  });

  it("opens repo tree inspector from an assistant file badge without auto-sending", async () => {
    const props = baseProps();
    mockFetchSequence(jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 123 }, { path: "README.md", type: "blob", size: 42 }], truncated: false }));
    renderWithProviders(<BuilderContainer {...props} mission="" repoReady={false} />);
    fireEvent.change(chatField(), { target: { value: "https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByText(/Repo geladen/)).toBeDefined());
    fireEvent.click(screen.getByLabelText("Repo Datei öffnen: src/App.tsx"));
    expect(screen.getByTestId("repo-tree-explorer")).toBeDefined();
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

  it("copies visible bubble text from the long-press menu without hidden metadata", async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText }, vibrate: vi.fn() });
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.contextMenu(screen.getByText("Package summary"));
    fireEvent.click(screen.getByText("📋 Kopieren"));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Package summary"));
  });

  it("fills composer from long-press follow-up without auto-sending", () => {
    const props = baseProps();
    renderWithProviders(<BuilderContainer {...props} />);
    fireEvent.contextMenu(screen.getByText("Package summary"));
    fireEvent.click(screen.getByText("💬 Zitieren"));
    expect(chatField().value).toContain("Package summary");
    expect(props.onMissionChange).not.toHaveBeenCalled();
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
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
    const props = { ...baseProps(), agentReady: true, onStartAgent: vi.fn() };
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
    await waitFor(() =>
      expect(screen.getByText(/Ausführungsauftrag erkannt/i)).toBeDefined(),
    );
    await waitFor(() => expect(props.onStartAgent).toHaveBeenCalledOnce());
    expect(screen.getByText(/Job-Start wurde angefragt/i)).toBeDefined();
    expect(screen.queryByText(/Sovereign Agent Runtime wird gestartet/i)).toBeNull();
    expect(screen.getByText(/kein Auto-Merge/i)).toBeDefined();
  });

  it("reports a failed Sovereign Agent start as terminal runtime state", async () => {
    const props = {
      ...baseProps(),
      agentReady: true,
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
    await waitFor(() => expect(props.onStartAgent).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(screen.getByText(/Sovereign Agent Runtime konnte nicht gestartet werden/i)).toBeDefined(),
    );
    expect(screen.getByText(/Backend session missing/i)).toBeDefined();
    expect(screen.queryByText(/Job-Start wurde angefragt; bestätigter Job-State/i)).toBeNull();
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

  it("answers 'arbeitet er schon?' locally only for the loaded repo job", async () => {
    const fetchMock = mockFetchSequence(
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
    const callsBeforeStatus = nonAuthFetchCalls(fetchMock).length;
    fireEvent.change(chatField(), { target: { value: "arbeitet er schon?" } });
    fireEvent.click(sendButton());
    await waitFor(() =>
      expect(screen.getByText(/Ja, Sovereign Agent läuft/i)).toBeDefined(),
    );
    expect(nonAuthFetchCalls(fetchMock)).toHaveLength(callsBeforeStatus);
  });

  it("answers executor status question locally when executor is idle (no job running, no workerBlocker)", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ choices: [{ message: { content: "Worker reply" } }] }),
    );
    // No workerBlocker → executor status question still answered locally (honest idle state)
    renderWithProviders(<BuilderContainer {...baseProps()} agentReady />);
    fireEvent.change(chatField(), { target: { value: "ist er fertig?" } });
    fireEvent.click(sendButton());
    await waitFor(() =>
      expect(screen.getByText(/Nein/i)).toBeDefined(),
    );
    // Status answered locally — no Worker call
    expect(nonAuthFetchCalls(fetchMock)).toHaveLength(0);
  });

  it("Worker HTTP 500 followed by 'Warum?' is answered locally — Worker not retried", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ error: { message: "Gateway exploded", type: "server_error" } }, 500),
      jsonResponse({ ok: true, provider: "sovereign-llm-bridge", gateway: "gatter", model: "cerebras/zai-glm-4.7", upstreamConfigured: true, secretConfigured: true }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} repoReady agentReady />);
    fireEvent.change(chatField(), { target: { value: "Hast du Vorschläge?" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByText(/Ich wiederhole den kaputten Worker-Call nicht blind/i)).toBeDefined());
    const callsAfterBlock = nonAuthFetchCalls(fetchMock).length;
    fireEvent.change(chatField(), { target: { value: "Warum?" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getAllByText(/Ich wiederhole den kaputten Worker-Call nicht blind/i).length).toBeGreaterThanOrEqual(2));
    // No extra fetch was made for the "Warum?" message
    expect(nonAuthFetchCalls(fetchMock)).toHaveLength(callsAfterBlock);
  });

  it("SovereignToolLauncher github_access opens the secure GitHubAccessCard directly", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    fireEvent.click(screen.getByLabelText("GitHub Access"));

    await waitFor(() => expect(screen.getByText(/GitHub-Zugang fehlt/i)).toBeDefined());
    expect(screen.getByText("Zugang eingeben")).toBeDefined();
    expect(screen.getByText(/Kein validierter GitHub-Zugang vorhanden/i)).toBeDefined();
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
    expect(screen.getByRole("log", { name: "Sovereign Action Stream" }))
      .toHaveTextContent("GitHub-Zugangsfläche geschlossen");
  });

  it("compact launcher trusts only a complete runtime repo snapshot, not the repoReady prop", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));

    const repoItem = screen.getByRole("menuitem", { name: "Repo" });
    const filesItem = screen.getByRole("menuitem", { name: "Files" });
    expect(repoItem).toHaveAttribute("data-gate-state", "setup_required");
    expect(repoItem.getAttribute("title")).toContain("Noch kein bestätigter Repo-Snapshot");
    expect(filesItem).toBeDisabled();
  });

  it("Repo shortcut opens a real setup surface and never an empty inspector", () => {
    renderWithProviders(<BuilderContainer {...baseProps()} />);
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Repo" }));

    expect(screen.getByRole("dialog", { name: "Repo Setup" })).toBeDefined();
    expect(screen.getByLabelText("GitHub Repository URL")).toBeDefined();
    expect(screen.queryByRole("dialog", { name: "Repo Inspector" })).toBeNull();
    expect(screen.getByRole("log", { name: "Sovereign Action Stream" })).toHaveTextContent("Repo-Setup geöffnet");
  });

  it("Files shortcut preserves its own intent and opens the confirmed file explorer", async () => {
    mockFetchSequence(
      jsonResponse({ tree: [{ path: "src/App.tsx", type: "blob", size: 42 }], truncated: false }),
    );
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} />);
    fireEvent.change(chatField(), { target: { value: "https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByText(/Repo geladen/)).toBeDefined());

    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    const filesItem = screen.getByRole("menuitem", { name: "Files" });
    expect(filesItem).toHaveAttribute("data-gate-state", "ready");
    fireEvent.click(filesItem);

    expect(screen.getByRole("dialog", { name: "Repo Inspector" })).toBeDefined();
    const actionStream = screen.getByRole("log", { name: "Sovereign Action Stream" });
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
    const actionStream = screen.getByRole("log", { name: "Sovereign Action Stream" });
    expect(actionStream).toHaveTextContent("Diff-Prüfung geöffnet");
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(actionStream.querySelector('[data-route="diff"]')).not.toBeNull();
    expect(chatField().value).toBe(before);
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
    expect(diffItem).toBeDisabled();
    expect(diffItem.getAttribute("title")).toContain("Kein Diff");
    expect(screen.queryByText("src/Foreign.tsx")).toBeNull();
    expect(screen.queryByText(/Draft PR öffnen/i)).toBeNull();
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
    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} />);
    await loadRepoFromChat();
    await validateGitHubAccessFromLauncher();

    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    expect(screen.getByRole("menuitem", { name: "GitHub Access" }).getAttribute("title")).toContain("Validiert");
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));

    await loadRepoUrlFromChat(SECOND_REPO_URL);
    const actionStream = screen.getByRole("log", { name: "Sovereign Action Stream" });
    expect(actionStream).not.toHaveTextContent("GitHub-Zugang bereit");
    expect(actionStream).toHaveTextContent("Repo-Kontext geladen");
    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    const accessItem = screen.getByRole("menuitem", { name: "GitHub Access" });
    expect(accessItem.getAttribute("title")).toContain("Zugang fehlt");
    expect(accessItem.getAttribute("title")).not.toContain("Validiert");
  });

  it("discards a GitHub validation result that finishes after the repo scope changed", async () => {
    let resolveUser: ((response: Response) => void) | null = null;
    const pendingUser = new Promise<Response>((resolve) => { resolveUser = resolve; });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (isAuthBootstrapRequest(input)) return authBootstrapResponse();
      const url = requestUrl(input);
      if (url.endsWith('/user')) return pendingUser;
      if (url.includes('/git/trees/')) {
        return jsonResponse({ tree: [{ path: url.includes('Other-Studio') ? 'src/Other.tsx' : 'README.md', type: 'blob', size: 12 }], truncated: false });
      }
      if (url.includes('/repos/') && url.includes('/collaborators/')) return jsonResponse({ permissions: { push: true } });
      return jsonResponse({ choices: [{ message: { content: 'unused' } }] });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} />);
    await loadRepoFromChat();
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    fireEvent.click(screen.getByLabelText('GitHub Access'));
    fireEvent.click(screen.getByText('Zugang eingeben'));
    fireEvent.change(screen.getByLabelText(/GitHub Token/i), { target: { value: fakeGitHubPat() } });
    fireEvent.click(screen.getByText('Übernehmen'));
    await waitFor(() =>
      expect(screen.getByRole('log', { name: 'Sovereign Action Stream' })).toHaveTextContent('GitHub-Zugang wird geprüft'),
    );

    await loadRepoUrlFromChat(SECOND_REPO_URL);
    resolveUser?.(jsonResponse({ login: 'octo' }));

    await waitFor(() =>
      expect(screen.getByRole('log', { name: 'Sovereign Action Stream' })).toHaveTextContent('GitHub-Zugangsprüfung verworfen'),
    );
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    expect(screen.getByRole('menuitem', { name: 'GitHub Access' }).getAttribute('title')).toContain('Zugang fehlt');
  });

  it("README & Docs preset opens real repo setup before GitHub access when repo evidence is missing", async () => {
    renderWithProviders(<BuilderContainer {...baseProps()} agentReady={false} />);
    fireEvent.click(screen.getByRole("button", { name: /README & Docs aktualisieren/i }));

    expect(screen.getByRole("dialog", { name: "Repo Setup" })).toBeDefined();
    expect(screen.getByLabelText("GitHub Repository URL")).toBeDefined();
    expect(screen.getByText(/Das echte Repo-Setup wurde geöffnet/i)).toBeDefined();
    expect(screen.queryByText("Zugang eingeben")).toBeNull();
  });

  it("allowed Draft-PR bridge route is not rendered as an execution blocker", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ tree: [{ path: "README.md", type: "blob", size: 42 }], truncated: false }),
      jsonResponse({ login: "octo" }),
      jsonResponse({ permissions: { push: true } }),
    );

    renderWithProviders(<BuilderContainer {...baseProps()} mission="" repoReady={false} agentReady={false} />);
    fireEvent.change(chatField(), { target: { value: "https://github.com/OuroborosCollective/Sovereign-Studio-ato" } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByText(/Repo geladen/)).toBeDefined());

    fireEvent.click(screen.getByLabelText("Tool Launcher öffnen"));
    fireEvent.click(screen.getByLabelText("GitHub Access"));
    fireEvent.click(screen.getByText("Zugang eingeben"));
    fireEvent.change(screen.getByLabelText(/GitHub Token/i), { target: { value: fakeGitHubPat() } });
    fireEvent.click(screen.getByText("Übernehmen"));
    await waitFor(() => expect(screen.getByText(/GitHub-Zugang ist bereit/i)).toBeDefined());

    fireEvent.change(chatField(), { target: { value: "Erstelle einen Draft PR für README und Docs." } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(screen.getByText(/Route gewählt: Patch\/Draft-PR Runtime/i)).toBeDefined());
    expect(screen.queryByText(/Ausführungsauftrag kann nicht ausgeführt werden/i)).toBeNull();
    expect(nonAuthFetchCalls(fetchMock).length).toBeGreaterThanOrEqual(3);
  });});
