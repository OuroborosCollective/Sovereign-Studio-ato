import React from 'react';
import { Activity, Database, GitPullRequestDraft, Network, Server, ShieldCheck } from 'lucide-react';
import { Modal } from '../Modal';
import { useSovereignAdapter } from '../../adapter/context';

const ENDPOINTS = [
  ['POST', '/api/user/agent/swarm/run', 'Persist and execute a mission through the Agents SDK control plane.'],
  ['GET', '/api/user/agent/swarm/runs/:runId', 'Read the persisted run identity and state.'],
  ['POST', '/api/user/agent/swarm/runs/:runId/resume', 'Resume one eligible persisted run with owner-supplied evidence.'],
  ['GET', '/api/user/agent/jobs/:jobId', 'Read the linked implementation job.'],
  ['POST', '/api/user/agent/jobs/:jobId/cancel', 'Cancel a linked implementation job.'],
  ['GET', '/api/user/agent/jobs/:jobId/evidence-anchors', 'Read revision-bound workspace evidence.'],
  ['POST', '/api/user/agent/jobs/:jobId/draft-pr/prepare', 'Read the publication gate. No PR is created.'],
  ['POST', '/api/user/agent/jobs/:jobId/draft-pr/create', 'Create a Draft PR only; response must contain strict GitHub readback evidence.'],
  ['GET', '/api/user/agent/toolchain/manifest', 'Read server-owned embedded toolchain policy.'],
  ['GET', '/api/user/agent/swarm/manifest', 'Read the live swarm/agent contract.'],
] as const;

export function ArchitectureModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const adapter = useSovereignAdapter();
  const status = adapter.getStatus?.();
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="PRODUCTION ADAPTER // TRUTH BOUNDARY">
      <div className="space-y-4 font-mono text-xs">
        <div className="p-3 rounded-lg border border-[rgba(16,185,129,0.3)] bg-[rgba(16,185,129,0.06)] flex items-start gap-3">
          <ShieldCheck size={18} className="text-[var(--emerald-seal)] shrink-0" />
          <div><div className="font-black text-white tracking-wider">NO AUTOMATIC SIMULATOR FALLBACK</div><div className="text-[var(--text-muted)] mt-1">Production UI state comes from authenticated backend readback. Backend failure remains visible as blocked/error state; it is never replaced by a mock success.</div></div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="p-3 rounded border border-white/5 bg-[var(--carbon-surface)]"><div className="text-[9px] text-[var(--text-dim)]">ADAPTER MODE</div><div className="mt-1 text-white font-bold">{status?.mode ?? 'live_http'}</div></div>
          <div className="p-3 rounded border border-white/5 bg-[var(--carbon-surface)]"><div className="text-[9px] text-[var(--text-dim)]">BACKEND</div><div className="mt-1 text-white font-bold truncate">{status?.backendUrl ?? 'same-origin/configured'}</div></div>
        </div>
        <div className="p-3 rounded-lg border border-[rgba(255,30,56,0.2)] bg-[var(--carbon-deep)]">
          <div className="flex items-center gap-2 font-black text-white tracking-wider mb-2"><Network size={14} className="text-[var(--red-laser)]" /> SINGLE EFFECT BOUNDARY</div>
          <pre className="whitespace-pre-wrap text-[10px] leading-relaxed text-[var(--text-muted)]">{`Human Mission\n   ↓\nSovereign Control Surface vNext\n   ↓\nSovereignBackendAdapter\n   ↓\nSovereignProductionAdapter\n   ↓ credentials: include\nAuthenticated Sovereign backend\n   ↓\nAgents SDK / implementation job / evidence / Draft PR gate\n   ↓\nGitHub readback → only then verified publication UI`}</pre>
        </div>
        <div>
          <div className="flex items-center gap-2 font-black text-white tracking-wider mb-2"><Server size={14} className="text-[var(--red-laser)]" /> BOUND ENDPOINTS</div>
          <div className="space-y-1.5">{ENDPOINTS.map(([method, path, note]) => <div key={`${method}-${path}`} className="p-2.5 rounded border border-white/5 bg-[var(--carbon-surface)] grid grid-cols-[45px_1fr] gap-2"><span className="text-[var(--red-laser)] font-black">{method}</span><div><code className="text-white break-all">{path}</code><div className="mt-1 text-[9.5px] text-[var(--text-muted)]">{note}</div></div></div>)}</div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-[9px]">
          <div className="p-2 border border-white/5 rounded"><Database size={13} className="mx-auto mb-1 text-[var(--text-muted)]" />SERVER SESSION<br/>HTTP-ONLY</div>
          <div className="p-2 border border-white/5 rounded"><Activity size={13} className="mx-auto mb-1 text-[var(--text-muted)]" />POLL UNTIL<br/>TERMINAL</div>
          <div className="p-2 border border-white/5 rounded"><GitPullRequestDraft size={13} className="mx-auto mb-1 text-[var(--text-muted)]" />DRAFT PR<br/>NO AUTO-MERGE</div>
        </div>
      </div>
    </Modal>
  );
}
