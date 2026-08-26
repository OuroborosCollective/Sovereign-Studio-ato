import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  DEV_CHAT_WORKER_DEFAULT_MODEL,
  fetchDevChatWorkerHealth,
  fetchDevChatWorkerReply,
  fetchSovereignLlmRouteCatalog,
  type DevChatWorkerMessage,
  type SovereignLlmRouteOption,
} from '../product/runtime/devChatWorkerBridge';
import { evaluateInputPolicy } from '../product/runtime/secureInputGuard';
import { LoginModal } from '../user/components/LoginModal';
import { useUserStore } from '../user/useUserStore';

type ChatRole = 'user' | 'assistant' | 'system';

interface ChatEntry {
  readonly id: string;
  readonly role: ChatRole;
  readonly text: string;
  readonly createdAt: number;
}

const C = {
  bg: '#0b0f14',
  surface: '#121821',
  surface2: '#171f2b',
  border: '#263244',
  text: '#edf3fa',
  sub: '#9aa9ba',
  muted: '#657487',
  accent: '#58a6ff',
  green: '#39d98a',
  amber: '#f2b84b',
  rose: '#ff6b7a',
};

function routeLabel(route: SovereignLlmRouteOption): string {
  const billing = route.billingCategory === 'free' ? 'FREE' : (route.billingCategory ?? 'STANDARD').toUpperCase();
  return `${billing} · ${route.label}`;
}

function Bubble({ entry }: { readonly entry: ChatEntry }) {
  const user = entry.role === 'user';
  const system = entry.role === 'system';
  return (
    <div
      data-role={entry.role}
      style={{
        display: 'flex',
        justifyContent: user ? 'flex-end' : 'flex-start',
        padding: '4px 0',
      }}
    >
      <div
        style={{
          maxWidth: system ? '92%' : 'min(86%, 760px)',
          padding: system ? '8px 11px' : '11px 13px',
          borderRadius: system ? 9 : user ? '15px 15px 4px 15px' : '15px 15px 15px 4px',
          border: `1px solid ${system ? C.amber + '55' : user ? C.accent + '55' : C.border}`,
          background: system ? C.amber + '0f' : user ? '#123054' : C.surface2,
          color: system ? C.amber : C.text,
          whiteSpace: 'pre-wrap',
          overflowWrap: 'anywhere',
          fontSize: system ? 12 : 14,
          lineHeight: 1.55,
          boxShadow: system ? 'none' : '0 5px 18px rgba(0,0,0,.16)',
        }}
      >
        {entry.text}
      </div>
    </div>
  );
}

export function PlayReleaseChat() {
  const { user, refreshUser, logout } = useUserStore();
  const [showLogin, setShowLogin] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [routes, setRoutes] = useState<readonly SovereignLlmRouteOption[]>([]);
  const [selectedRoute, setSelectedRoute] = useState('');
  const [routeError, setRouteError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runtimeState, setRuntimeState] = useState<'checking' | 'ready' | 'degraded'>('checking');
  const [lastFailedText, setLastFailedText] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const sequenceRef = useRef(0);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  useEffect(() => {
    if (!user) {
      setRoutes([]);
      setRouteError(null);
      setRuntimeState('checking');
      return;
    }
    const controller = new AbortController();
    let active = true;
    void Promise.allSettled([
      fetchSovereignLlmRouteCatalog(controller.signal, 'picker'),
      fetchDevChatWorkerHealth(controller.signal),
    ]).then(([catalog, health]) => {
      if (!active) return;
      if (catalog.status === 'fulfilled') {
        setRoutes(catalog.value);
        setRouteError(null);
      } else {
        setRoutes([]);
        setRouteError('Routenkatalog ist gerade nicht verfügbar.');
      }
      if (health.status === 'fulfilled' && health.value.ok) setRuntimeState('ready');
      else setRuntimeState('degraded');
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [user]);

  useEffect(() => {
    const node = listRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  const model = selectedRoute || DEV_CHAT_WORKER_DEFAULT_MODEL;
  const activeRoute = useMemo(
    () => routes.find((route) => route.id === selectedRoute),
    [routes, selectedRoute],
  );

  const addMessage = (role: ChatRole, text: string) => {
    sequenceRef.current += 1;
    const entry: ChatEntry = {
      id: `release-chat-${sequenceRef.current}`,
      role,
      text: text.trim(),
      createdAt: Date.now(),
    };
    setMessages((current) => [...current.slice(-79), entry]);
  };

  const submit = async (override?: string) => {
    const text = (override ?? draft).trim();
    if (!text || busy) return;
    if (!user) {
      setShowLogin(true);
      return;
    }

    const inputPolicy = evaluateInputPolicy(text);
    if (inputPolicy.shouldBlock) {
      setDraft('');
      addMessage('system', 'Diese Eingabe sieht wie ein Zugangsschlüssel oder Secret aus und wurde nicht an das LLM gesendet.');
      return;
    }

    setDraft('');
    setBusy(true);
    setLastFailedText(null);
    addMessage('user', text);

    const conversation: DevChatWorkerMessage[] = [
      {
        role: 'system',
        content: 'Du bist Sovereign. Antworte hilfreich, klar und direkt. Behaupte keine ausgeführten Aktionen ohne echte Runtime-Evidence.',
      },
      ...messages
        .filter((entry) => entry.role === 'user' || entry.role === 'assistant')
        .slice(-18)
        .map((entry): DevChatWorkerMessage => ({
          role: entry.role as 'user' | 'assistant',
          content: entry.text,
        })),
      { role: 'user', content: text },
    ];

    try {
      const result = await fetchDevChatWorkerReply(
        { model, messages: conversation },
        { maxRetries: 1, retryDelayMs: 700 },
      );
      if (!result.ok || !result.content) {
        const detail = result.diagnostic?.nextAction || result.error || 'Die LLM-Runtime hat keine Antwort geliefert.';
        setLastFailedText(text);
        setRuntimeState('degraded');
        addMessage('system', `LLM-Anfrage blockiert: ${detail}`);
        return;
      }
      setRuntimeState('ready');
      const fallback = result.fallbackUsed && result.actualModel
        ? `\n\nHinweis: Antwort kam über ${result.actualModel}.`
        : '';
      addMessage('assistant', `${result.content}${fallback}`);
    } catch (error) {
      setLastFailedText(text);
      setRuntimeState('degraded');
      addMessage('system', `LLM-Verbindung fehlgeschlagen: ${error instanceof Error ? error.message : 'unbekannter Fehler'}`);
    } finally {
      setBusy(false);
    }
  };

  const runtimeColor = runtimeState === 'ready' ? C.green : runtimeState === 'degraded' ? C.amber : C.muted;
  const runtimeLabel = runtimeState === 'ready' ? 'LLM bereit' : runtimeState === 'degraded' ? 'LLM eingeschränkt' : 'LLM wird geprüft';

  return (
    <main
      data-testid="sovereign-release-chat"
      data-layout="play-release-chat"
      aria-label="Sovereign Chat"
      style={{
        height: '100dvh',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        background: C.bg,
        color: C.text,
        fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}
    >
      <style>{`
        * { box-sizing: border-box; }
        .release-chat-header { padding-top: max(10px, env(safe-area-inset-top)); }
        .release-chat-shell { width: 100%; max-width: 980px; margin: 0 auto; }
        .release-chat-composer { padding-bottom: max(10px, env(safe-area-inset-bottom)); }
        @media (max-width: 640px) {
          .release-chat-title-sub { display: none; }
          .release-chat-route { max-width: 145px !important; }
        }
      `}</style>

      <header
        className="release-chat-header"
        style={{ flexShrink: 0, borderBottom: `1px solid ${C.border}`, background: C.surface }}
      >
        <div className="release-chat-shell" style={{ minHeight: 58, display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px' }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, display: 'grid', placeItems: 'center', background: C.accent + '18', border: `1px solid ${C.accent}44`, color: C.accent, fontWeight: 800 }}>S</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontWeight: 750, fontSize: 15 }}>Sovereign</div>
            <div className="release-chat-title-sub" style={{ color: C.sub, fontSize: 10.5 }}>Chat · stabiler Play-Release-Modus</div>
          </div>
          {user && (
            <select
              className="release-chat-route"
              aria-label="LLM Route"
              value={selectedRoute}
              onChange={(event) => setSelectedRoute(event.target.value)}
              style={{
                maxWidth: 230,
                minHeight: 40,
                borderRadius: 8,
                border: `1px solid ${C.border}`,
                background: C.bg,
                color: C.text,
                padding: '0 8px',
                fontSize: 11,
              }}
            >
              <option value="">Auto · FreeLLM zuerst</option>
              {routes.map((route) => <option key={route.id} value={route.id}>{routeLabel(route)}</option>)}
            </select>
          )}
          <span title={routeError ?? runtimeLabel} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: runtimeColor, fontSize: 10, whiteSpace: 'nowrap' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: runtimeColor }} />
            <span className="release-chat-title-sub">{runtimeLabel}</span>
          </span>
          {user ? (
            <button
              type="button"
              onClick={() => { void logout(); }}
              title={user.email}
              aria-label="Abmelden"
              style={{ minWidth: 44, minHeight: 44, borderRadius: 9, border: `1px solid ${C.border}`, background: C.bg, color: C.sub, cursor: 'pointer' }}
            >
              ↪
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setShowLogin(true)}
              style={{ minHeight: 44, padding: '0 14px', borderRadius: 9, border: `1px solid ${C.accent}66`, background: C.accent + '16', color: C.accent, fontWeight: 700, cursor: 'pointer' }}
            >
              Anmelden
            </button>
          )}
        </div>
      </header>

      <div ref={listRef} className="release-chat-shell" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 14px 20px', scrollBehavior: 'smooth' }}>
        {messages.length === 0 ? (
          <div style={{ minHeight: '55vh', display: 'grid', placeItems: 'center', textAlign: 'center', padding: 20 }}>
            <div style={{ maxWidth: 520 }}>
              <div style={{ width: 54, height: 54, margin: '0 auto 16px', borderRadius: 16, display: 'grid', placeItems: 'center', color: C.accent, background: C.accent + '12', border: `1px solid ${C.accent}33`, fontSize: 22, fontWeight: 800 }}>S</div>
              <h1 style={{ margin: 0, fontSize: 22, letterSpacing: '-.02em' }}>Was möchtest du wissen oder erledigen?</h1>
              <p style={{ color: C.sub, fontSize: 13, lineHeight: 1.6, margin: '10px auto 0' }}>
                Sovereign nutzt den aktuellen serverseitigen LLM-Routenkatalog. Zugangsdaten bleiben außerhalb des Chats.
              </p>
              {!user && <button type="button" onClick={() => setShowLogin(true)} style={{ marginTop: 18, minHeight: 44, padding: '0 18px', borderRadius: 10, border: 'none', background: C.accent, color: '#07111c', fontWeight: 800, cursor: 'pointer' }}>Mit E-Mail anmelden</button>}
            </div>
          </div>
        ) : messages.map((entry) => <Bubble key={entry.id} entry={entry} />)}
        {busy && (
          <div role="status" style={{ color: C.sub, fontSize: 12, padding: '8px 3px' }}>Sovereign antwortet…</div>
        )}
      </div>

      <footer className="release-chat-composer" style={{ flexShrink: 0, borderTop: `1px solid ${C.border}`, background: C.surface }}>
        <div className="release-chat-shell" style={{ padding: '10px 12px 0' }}>
          {activeRoute && <div style={{ color: C.muted, fontSize: 9.5, marginBottom: 5 }}>Route fixiert: {routeLabel(activeRoute)} · kein stiller Routenwechsel</div>}
          {lastFailedText && !busy && (
            <button type="button" onClick={() => { void submit(lastFailedText); }} style={{ marginBottom: 7, minHeight: 36, padding: '0 11px', borderRadius: 8, border: `1px solid ${C.amber}55`, background: C.amber + '10', color: C.amber, cursor: 'pointer' }}>
              Letzte Anfrage erneut versuchen
            </button>
          )}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
            <textarea
              aria-label="Nachricht an Sovereign"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
                }
              }}
              disabled={busy}
              placeholder={user ? 'Nachricht an Sovereign…' : 'Zum Chatten bitte anmelden…'}
              rows={1}
              style={{
                flex: 1,
                minWidth: 0,
                minHeight: 46,
                maxHeight: 150,
                resize: 'vertical',
                borderRadius: 12,
                border: `1px solid ${C.border}`,
                background: C.bg,
                color: C.text,
                padding: '12px 13px',
                font: '14px/1.45 inherit',
                outline: 'none',
              }}
            />
            <button
              type="button"
              aria-label="Senden"
              disabled={busy || !draft.trim()}
              onClick={() => { void submit(); }}
              style={{ width: 46, height: 46, flexShrink: 0, borderRadius: 12, border: 'none', background: busy || !draft.trim() ? C.border : C.accent, color: '#07111c', fontSize: 18, fontWeight: 800, cursor: busy || !draft.trim() ? 'not-allowed' : 'pointer' }}
            >
              ↑
            </button>
          </div>
          <div style={{ minHeight: 25, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, color: C.muted, fontSize: 9.5 }}>
            <span>{user ? user.email : 'E-Mail/Passwort-Anmeldung erforderlich'}</span>
            <span>{routeError ?? 'Enter sendet · Shift+Enter neue Zeile'}</span>
          </div>
        </div>
      </footer>

      {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
    </main>
  );
}

export default PlayReleaseChat;
