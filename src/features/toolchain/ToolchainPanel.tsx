/**
 * ToolchainPanel — Launcher-Tool für den Sovereign Universal Toolchain Server.
 *
 * Ermöglicht Admins und LLM-Workspaces:
 *  - Alle verfügbaren Tools zu sehen (Manifest)
 *  - Tools manuell über ein JSON-Form aufzurufen
 *  - Ergebnisse als formatierten JSON zu lesen
 *  - MCP/REST-Endpunkte für externe LLM-Clients zu kopieren
 *
 * Integrations-Endpunkte die angezeigt werden:
 *   MCP:     https://sovereign-backend.arelorian.de/toolchain/mcp
 *   REST:    https://sovereign-backend.arelorian.de/toolchain/api/v1/tools/{name}
 *   OpenAPI: https://sovereign-backend.arelorian.de/toolchain/api/openapi.json
 */

import React, { useState } from 'react';
import {
  Wrench, Zap, Copy, CheckCircle, AlertTriangle, Loader2,
  ChevronDown, ChevronRight, Globe, ExternalLink, RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { useToolchain } from './useToolchain';
import type { ToolDefinition } from './toolchainClient';
import type { LauncherToolProps } from '../launcher/launcherRegistry';

const C = {
  bg: '#0e1116', surface: '#161c24', border: '#232d3a',
  accent: '#00d9b1', text: '#cdd9e5', textSub: '#768390',
  amber: '#f59e0b', danger: '#f87171', green: '#34d399',
} as const;

const TC_BASE = 'https://sovereign-backend.arelorian.de/toolchain';

// ── Endpoint Info Row ─────────────────────────────────────────────────────────

function EndpointRow({ label, url }: { label: string; url: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(url).catch(() => undefined);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: `1px solid ${C.border}` }}>
      <span style={{ fontSize: 10, fontWeight: 700, color: C.textSub, minWidth: 64 }}>{label}</span>
      <span style={{ flex: 1, fontSize: 10, fontFamily: 'monospace', color: C.accent, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{url}</span>
      <button type="button" onClick={handleCopy}
        style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: copied ? C.green : C.textSub, padding: 0, flexShrink: 0 }}>
        {copied ? <CheckCircle size={12} /> : <Copy size={12} />}
      </button>
      <a href={url} target="_blank" rel="noreferrer"
        style={{ color: C.textSub, display: 'flex', flexShrink: 0 }}>
        <ExternalLink size={12} />
      </a>
    </div>
  );
}

// ── Tool Card ─────────────────────────────────────────────────────────────────

function ToolCard({
  tool,
  onInvoke,
  invoking,
}: {
  tool: ToolDefinition;
  onInvoke: (name: string, args: Record<string, unknown>) => void;
  invoking: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [argsJson, setArgsJson] = useState('{}');
  const [argsError, setArgsError] = useState<string | null>(null);

  const validate = (v: string) => {
    try { JSON.parse(v); setArgsError(null); } catch { setArgsError('Ungültiges JSON'); }
  };

  const handleRun = () => {
    try {
      const parsed = JSON.parse(argsJson) as Record<string, unknown>;
      onInvoke(tool.name, parsed);
    } catch { setArgsError('Ungültiges JSON'); }
  };

  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden', marginBottom: 6 }}>
      <div
        onClick={() => setExpanded(v => !v)}
        style={{ padding: '8px 12px', display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer', background: expanded ? `${C.accent}08` : 'transparent' }}
      >
        <span style={{ marginTop: 1, color: expanded ? C.accent : C.textSub, flexShrink: 0 }}>
          {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: C.text, fontFamily: 'monospace' }}>{tool.name}</span>
            {tool.write_action && (
              <span style={{ fontSize: 8, fontWeight: 800, color: C.amber, background: `${C.amber}20`, padding: '1px 5px', borderRadius: 4 }}>WRITE</span>
            )}
            {tool.requires_confirm && (
              <span style={{ fontSize: 8, fontWeight: 800, color: C.danger, background: `${C.danger}20`, padding: '1px 5px', borderRadius: 4 }}>CONFIRM</span>
            )}
          </div>
          <div style={{ fontSize: 10, color: C.textSub, marginTop: 2, lineHeight: 1.4 }}>{tool.description}</div>
        </div>
      </div>

      {expanded && (
        <div style={{ padding: '0 12px 12px', background: C.surface, borderTop: `1px solid ${C.border}` }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: C.textSub, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '10px 0 4px' }}>
            Args (JSON)
          </div>
          <textarea
            value={argsJson}
            onChange={e => { setArgsJson(e.target.value); validate(e.target.value); }}
            rows={4}
            style={{
              width: '100%', boxSizing: 'border-box',
              background: C.bg, border: `1px solid ${argsError ? C.danger : C.border}`,
              borderRadius: 6, padding: '6px 8px', fontSize: 10, fontFamily: 'monospace',
              color: C.text, resize: 'vertical', outline: 'none',
            }}
          />
          {argsError && <div style={{ fontSize: 9, color: C.danger, marginTop: 2 }}>{argsError}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
            <button
              type="button"
              onClick={handleRun}
              disabled={invoking || !!argsError}
              style={{
                background: C.accent, border: 'none', borderRadius: 6,
                padding: '5px 14px', fontSize: 10, fontWeight: 700, color: '#000',
                cursor: (invoking || !!argsError) ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: 4,
                opacity: (invoking || !!argsError) ? 0.6 : 1,
              }}
            >
              {invoking ? <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} /> : <Zap size={10} />}
              Ausführen
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Result View ───────────────────────────────────────────────────────────────

function ResultView({ result }: { result: { ok: boolean; tool: string; result?: unknown; error?: string } }) {
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(result, null, 2);

  return (
    <div style={{ background: C.surface, border: `1px solid ${result.ok ? C.green + '40' : C.danger + '40'}`, borderRadius: 8, overflow: 'hidden' }}>
      <div style={{ padding: '6px 10px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 6 }}>
        {result.ok
          ? <CheckCircle size={12} color={C.green} />
          : <AlertTriangle size={12} color={C.danger} />}
        <span style={{ fontSize: 10, fontWeight: 700, color: result.ok ? C.green : C.danger }}>
          {result.ok ? 'Erfolgreich' : 'Fehler'} — {result.tool}
        </span>
        <button type="button" onClick={() => { navigator.clipboard.writeText(json).catch(() => undefined); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
          style={{ marginLeft: 'auto', background: 'transparent', border: 'none', cursor: 'pointer', color: copied ? C.green : C.textSub, padding: 0 }}>
          {copied ? <CheckCircle size={11} /> : <Copy size={11} />}
        </button>
      </div>
      <pre style={{ margin: 0, padding: '8px 10px', fontSize: 9, fontFamily: 'monospace', color: C.text, overflow: 'auto', maxHeight: 240 }}>
        {json}
      </pre>
    </div>
  );
}

// ── Main Panel ────────────────────────────────────────────────────────────────

export function ToolchainPanel(_props: LauncherToolProps) {
  const { tools, loading, error, serverOnline, invoke, lastResult, invoking, reload } = useToolchain();
  const [filter, setFilter] = useState('');

  const filtered = tools.filter(t =>
    !filter || t.name.includes(filter.toLowerCase()) || t.description.toLowerCase().includes(filter.toLowerCase())
  );

  const readTools  = filtered.filter(t => !t.write_action);
  const writeTools = filtered.filter(t => t.write_action);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: C.bg, overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '12px 14px', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <Wrench size={16} color={C.accent} />
          <span style={{ fontSize: 13, fontWeight: 800, color: C.text }}>Universal Toolchain</span>
          <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4, fontSize: 9, fontWeight: 700,
            color: serverOnline ? C.green : (loading ? C.amber : C.danger),
            background: serverOnline ? `${C.green}15` : `${C.danger}15`, padding: '2px 7px', borderRadius: 4 }}>
            <Globe size={9} />
            {loading ? 'VERBINDE…' : serverOnline ? 'ONLINE' : 'OFFLINE'}
          </span>
          <button type="button" onClick={reload}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: C.textSub, padding: 0 }}>
            <RefreshCw size={13} />
          </button>
        </div>

        {/* Endpoints */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: '6px 10px' }}>
          <EndpointRow label="MCP"     url={`${TC_BASE}/mcp`} />
          <EndpointRow label="REST"    url={`${TC_BASE}/api/v1/tools/{name}`} />
          <EndpointRow label="OpenAPI" url={`${TC_BASE}/api/openapi.json`} />
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {loading && (
          <div style={{ textAlign: 'center', padding: 24, color: C.textSub, fontSize: 12, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
            <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />Manifest wird geladen…
          </div>
        )}

        {error && (
          <div style={{ background: `${C.danger}15`, border: `1px solid ${C.danger}30`, borderRadius: 8, padding: '10px 12px', display: 'flex', gap: 8 }}>
            <AlertTriangle size={13} color={C.danger} style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: C.danger }}>Server nicht erreichbar</div>
              <div style={{ fontSize: 10, color: C.textSub, marginTop: 2 }}>{error}</div>
            </div>
          </div>
        )}

        {!loading && serverOnline && (
          <>
            <input
              placeholder="Tools filtern…"
              value={filter}
              onChange={e => setFilter(e.target.value)}
              style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6, padding: '6px 10px', fontSize: 11, color: C.text, outline: 'none' }}
            />

            {/* Read-only tools */}
            {readTools.length > 0 && (
              <div>
                <div style={{ fontSize: 9, fontWeight: 700, color: C.textSub, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
                  Read-only Tools ({readTools.length})
                </div>
                {readTools.map(t => (
                  <ToolCard key={t.name} tool={t} onInvoke={(n, a) => void invoke(n, a)} invoking={invoking} />
                ))}
              </div>
            )}

            {/* Write tools */}
            {writeTools.length > 0 && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <ShieldAlert size={11} color={C.amber} />
                  <span style={{ fontSize: 9, fontWeight: 700, color: C.amber, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    Write Tools ({writeTools.length}) — confirm=true erforderlich
                  </span>
                </div>
                {writeTools.map(t => (
                  <ToolCard key={t.name} tool={t} onInvoke={(n, a) => void invoke(n, a)} invoking={invoking} />
                ))}
              </div>
            )}
          </>
        )}

        {/* Last result */}
        {lastResult && (
          <div>
            <div style={{ fontSize: 9, fontWeight: 700, color: C.textSub, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
              Letztes Ergebnis
            </div>
            <ResultView result={lastResult} />
          </div>
        )}
      </div>

      <style>{`@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }`}</style>
    </div>
  );
}
