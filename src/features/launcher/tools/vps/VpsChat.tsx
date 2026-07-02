/**
 * VpsChat — No-Code Chat für den VPS Connector.
 *
 * Flow: Natürlichsprache → Gemini → Shell-Befehl → User-Bestätigung → Ausführung
 * Destructive Commands (rm -rf, mkfs etc.) → Warn-Dialog vor Bestätigung.
 * KEIN Auto-Execute — User bestätigt jeden Befehl explizit.
 *
 * Issue #454
 */

import React, { useState, useRef, useEffect } from 'react';
import { Send, AlertTriangle, CheckCircle, XCircle, Terminal, Loader2 } from 'lucide-react';
import { geminiService } from '../../../ai/geminiService';
import { useLauncherContext } from '../../LauncherContext';
import type { ExecResult } from './useVpsConnection';

const C = {
  bg:      '#0e1116',
  surface: '#161c24',
  border:  '#232d3a',
  accent:  '#00d9b1',
  text:    '#cdd9e5',
  textSub: '#768390',
  violet:  '#8b5cf6',
  error:   '#f87171',
  warn:    '#fbbf24',
  green:   '#34d399',
} as const;

// Muster für destruktive Befehle
const DESTRUCTIVE_PATTERNS = [
  /rm\s+-[a-z]*rf?\s/i, /rm\s+-[a-z]*f[a-z]*\s/i,
  /mkfs\b/, /dd\s+if=/, /:\s*>\s*\//, /chmod\s+777/,
  /shutdown\b/, /reboot\b/, /init\s+0/, /poweroff\b/,
  /DROP\s+TABLE/i, /DROP\s+DATABASE/i, /truncate\s+table/i,
];

function isDestructive(cmd: string): boolean {
  return DESTRUCTIVE_PATTERNS.some((p) => p.test(cmd));
}

// ── Typen ────────────────────────────────────────────────────────────────────

type MessageRole = 'user' | 'assistant' | 'system' | 'exec-result';

interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  command?: string;       // Vorgeschlagener Befehl (wartet auf Bestätigung)
  execResult?: ExecResult;
  pending?: boolean;      // Wartet auf Bestätigung
  isDestructive?: boolean;
}

interface Props {
  host: string;
  username: string;
  execCommand: (cmd: string) => Promise<ExecResult>;
  onSelectFile?: (path: string) => void;
}

// ── Komponente ───────────────────────────────────────────────────────────────

export function VpsChat({ host, username, execCommand, onSelectFile }: Props) {
  const { geminiApiKey } = useLauncherContext();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'system',
      text: geminiApiKey
        ? `Verbunden mit ${username}@${host}. Beschreibe was du tun möchtest — ich schlage den passenden Befehl vor. Du bestätigst vor der Ausführung.`
        : `Verbunden mit ${username}@${host}. Kein Gemini-Key hinterlegt — gib Shell-Befehle direkt ein. Ich führe sie erst nach deiner Bestätigung aus.`,
    },
  ]);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSubmit() {
    const text = input.trim();
    if (!text || thinking) return;
    setInput('');

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', text };
    setMessages((m) => [...m, userMsg]);
    setThinking(true);

    try {
      let command: string;
      let destructive: boolean;

      if (geminiApiKey) {
        // Gemini: Natürlichsprache → Shell-Befehl
        const prompt = `Du bist ein Linux-Admin-Assistent. Der User ist per SSH verbunden mit ${username}@${host}.
Konvertiere die folgende Anfrage in GENAU EINEN Shell-Befehl. Antworte NUR mit dem Befehl, keine Erklärung, kein Markdown.

Anfrage: ${text}`;
        const result = await geminiService.generateText(geminiApiKey, prompt, {
          maxOutputTokens: 200,
          temperature: 0.1,
        });
        command = result.trim().replace(/^```[a-z]*\n?|\n?```$/g, '').trim();
      } else {
        // Ohne Gemini: Eingabe direkt als Befehl behandeln
        command = text;
      }

      destructive = isDestructive(command);

      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: destructive
          ? `⚠️ Destruktiver Befehl erkannt. Bitte prüfe sorgfältig:`
          : `Vorgeschlagener Befehl:`,
        command,
        pending: true,
        isDestructive: destructive,
      };
      setMessages((m) => [...m, assistantMsg]);
    } catch {
      setMessages((m) => [...m, {
        id: crypto.randomUUID(),
        role: 'system',
        text: 'Befehl konnte nicht übersetzt werden — gib ihn direkt ein:',
        command: text,
        pending: true,
        isDestructive: isDestructive(text),
      }]);
    } finally {
      setThinking(false);
    }
  }

  async function executeCommand(msgId: string, command: string) {
    // Befehl als "bestätigt" markieren
    setMessages((m) => m.map((msg) =>
      msg.id === msgId ? { ...msg, pending: false } : msg
    ));

    const loadingId = crypto.randomUUID();
    setMessages((m) => [...m, { id: loadingId, role: 'system', text: '⟳ Wird ausgeführt…' }]);

    try {
      const result = await execCommand(command);
      setMessages((m) => m.filter((msg) => msg.id !== loadingId).concat({
        id: crypto.randomUUID(),
        role: 'exec-result',
        text: '',
        execResult: result,
      }));
    } catch (err) {
      setMessages((m) => m.filter((msg) => msg.id !== loadingId).concat({
        id: crypto.randomUUID(),
        role: 'system',
        text: `Fehler: ${err instanceof Error ? err.message : 'Unbekannt'}`,
      }));
    }
  }

  function cancelCommand(msgId: string) {
    setMessages((m) => m.map((msg) =>
      msg.id === msgId ? { ...msg, pending: false, command: undefined } : msg
    ));
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            onExecute={executeCommand}
            onCancel={cancelCommand}
          />
        ))}
        {thinking && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: C.textSub }}>
            <Loader2 size={12} className="animate-spin" />
            <span style={{ fontSize: 11 }}>Gemini denkt…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        display: 'flex', gap: 8, padding: '10px 14px',
        borderTop: `1px solid ${C.border}`, flexShrink: 0,
      }}>
        <input
          style={{
            flex: 1, padding: '8px 12px', background: C.bg,
            border: `1px solid ${C.border}`, borderRadius: 8,
            color: C.text, fontSize: 12, outline: 'none',
          }}
          placeholder="Beschreibe was du tun möchtest…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSubmit(); } }}
          disabled={thinking}
        />
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={!input.trim() || thinking}
          style={{
            width: 36, height: 36, borderRadius: 8, border: 'none',
            background: input.trim() && !thinking ? C.violet : C.surface,
            color: '#fff', cursor: input.trim() && !thinking ? 'pointer' : 'not-allowed',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'background 0.15s',
          }}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}

// ── MessageBubble ─────────────────────────────────────────────────────────────

function MessageBubble({ msg, onExecute, onCancel }: {
  msg: ChatMessage;
  onExecute: (id: string, cmd: string) => void;
  onCancel: (id: string) => void;
}) {
  if (msg.role === 'user') {
    return (
      <div style={{ alignSelf: 'flex-end', maxWidth: '85%' }}>
        <div style={{
          padding: '8px 12px', borderRadius: '12px 12px 2px 12px',
          background: '#6366f140', border: '1px solid #6366f130',
          fontSize: 12, color: C.text,
        }}>
          {msg.text}
        </div>
      </div>
    );
  }

  if (msg.role === 'exec-result' && msg.execResult) {
    const { stdout, stderr, exitCode } = msg.execResult;
    return (
      <div style={{
        padding: '10px 12px', borderRadius: 8,
        background: exitCode === 0 ? 'rgba(52,211,153,0.06)' : 'rgba(248,113,113,0.06)',
        border: `1px solid ${exitCode === 0 ? 'rgba(52,211,153,0.2)' : 'rgba(248,113,113,0.2)'}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          {exitCode === 0
            ? <CheckCircle size={12} color={C.green} />
            : <XCircle size={12} color={C.error} />
          }
          <span style={{ fontSize: 10, color: C.textSub, fontWeight: 600 }}>
            Exit {exitCode}
          </span>
        </div>
        {stdout && (
          <pre style={{
            margin: 0, fontSize: 10, color: C.text,
            whiteSpace: 'pre-wrap', wordBreak: 'break-all',
            fontFamily: 'monospace', maxHeight: 200, overflowY: 'auto',
          }}>{stdout}</pre>
        )}
        {stderr && (
          <pre style={{
            margin: '4px 0 0', fontSize: 10, color: C.error,
            whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontFamily: 'monospace',
          }}>{stderr}</pre>
        )}
      </div>
    );
  }

  // assistant / system mit optionalem Befehl
  return (
    <div style={{ maxWidth: '95%' }}>
      {msg.text && (
        <div style={{ fontSize: 11, color: C.textSub, marginBottom: msg.command ? 6 : 0 }}>
          {msg.text}
        </div>
      )}
      {msg.command && msg.pending && (
        <div style={{
          padding: '10px 12px', borderRadius: 8,
          background: msg.isDestructive ? 'rgba(251,191,36,0.08)' : 'rgba(0,217,177,0.06)',
          border: `1px solid ${msg.isDestructive ? 'rgba(251,191,36,0.25)' : 'rgba(0,217,177,0.2)'}`,
        }}>
          {msg.isDestructive && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8 }}>
              <AlertTriangle size={12} color={C.warn} />
              <span style={{ fontSize: 10, color: C.warn, fontWeight: 700 }}>DESTRUKTIVER BEFEHL</span>
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
            <Terminal size={11} color={C.textSub} />
            <code style={{ fontSize: 11, color: C.text, fontFamily: 'monospace', flex: 1 }}>
              {msg.command}
            </code>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              type="button"
              onClick={() => onExecute(msg.id, msg.command!)}
              style={{
                flex: 1, padding: '6px 0', borderRadius: 7, border: 'none',
                background: msg.isDestructive ? C.warn : C.accent,
                color: msg.isDestructive ? '#000' : '#000',
                fontSize: 11, fontWeight: 700, cursor: 'pointer',
              }}
            >
              {msg.isDestructive ? '⚠ Trotzdem ausführen' : '✓ Ausführen'}
            </button>
            <button
              type="button"
              onClick={() => onCancel(msg.id)}
              style={{
                padding: '6px 14px', borderRadius: 7,
                border: `1px solid ${C.border}`, background: 'transparent',
                color: C.textSub, fontSize: 11, cursor: 'pointer',
              }}
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
