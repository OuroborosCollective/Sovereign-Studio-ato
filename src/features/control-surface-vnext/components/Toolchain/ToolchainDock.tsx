import React from 'react';
import { Activity, Check, Cpu, Shield } from 'lucide-react';
import { Modal } from '../Modal';
import type { Toolchain } from '../../types/domain';
import { cx } from '../../utils/cx';

interface Props { isOpen: boolean; onClose: () => void; toolchains: Toolchain[]; selectedToolchainId?: string; }

export function ToolchainDock({ isOpen, onClose, toolchains, selectedToolchainId }: Props) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="TOOLCHAIN CONFIGURATION // EXECUTION DRIVERS">
      <div className="space-y-3 font-mono">
        <div className="text-[11px] text-[var(--text-muted)] mb-2">Read-only server-owned execution manifest. vNext does not invent or locally switch runtime drivers.</div>
        {toolchains.map((tool) => {
          const active = selectedToolchainId ? selectedToolchainId === tool.id : tool.status === 'active';
          return <div key={tool.id} className={cx('p-3.5 border rounded-lg transition-all flex items-start gap-3 relative theme-diamond-cut', active ? 'border-[var(--red-laser)] bg-[rgba(255,30,56,0.12)] shadow-[0_0_15px_rgba(255,30,56,0.2)]' : 'border-white/5 bg-[var(--carbon-deep)]')}>
            <div className={cx('w-8 h-8 rounded flex items-center justify-center shrink-0 mt-0.5', active ? 'bg-[var(--red-pulse)] text-white shadow-[0_0_10px_#ff1e38]' : 'bg-[var(--carbon-surface)] text-[var(--text-dim)]')}><Cpu size={16} /></div>
            <div className="flex-1 min-w-0"><div className="flex items-center justify-between gap-2"><div className={cx('text-sm font-bold truncate', active ? 'text-white' : 'text-[var(--text-main)]')}>{tool.name}</div>{active && <span className="flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded bg-[var(--red-laser)] text-white font-bold"><Check size={10} /> ACTIVE</span>}</div><div className="text-[11.5px] text-[var(--text-muted)] font-sans mt-1 leading-normal">{tool.description}</div><div className="flex items-center gap-3 mt-2.5 text-[9.5px] text-[var(--text-dim)]">{tool.driver && <span className="flex items-center gap-1 text-white"><Shield size={10} className="text-[var(--red-laser)]" /> {tool.driver}</span>}{tool.latencyMs && <span className="flex items-center gap-1"><Activity size={10} /> {tool.latencyMs}ms LATENCY</span>}{tool.badge && <span className="px-1 py-0.2 rounded bg-white/5 text-[var(--text-muted)] border border-white/5">{tool.badge}</span>}</div></div>
          </div>;
        })}
        {toolchains.length === 0 && <div className="text-[var(--text-dim)] text-xs text-center py-6">No server toolchain manifest has been read back.</div>}
      </div>
    </Modal>
  );
}
