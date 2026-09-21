import React, { useEffect } from 'react';
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react';
import type { JobPhase } from '../../types/domain';
import { playAwakeningSound } from '../../utils/audio';

interface Props { isTyping?: boolean; jobPhase?: JobPhase; }

const ACTIVE = new Set<JobPhase>(['DISPATCHING', 'PROVISIONING', 'EXECUTING', 'FINALIZING', 'READY_TO_PUBLISH']);

function phaseLabel(phase: JobPhase): string {
  switch (phase) {
    case 'AWAKENING': return 'NEURAL CONTACT';
    case 'DISPATCHING': return 'RUN DISPATCH';
    case 'PROVISIONING': return 'WORKSPACE PROVISION';
    case 'EXECUTING': return 'RUNTIME EXECUTION';
    case 'AWAITING_OWNER_INPUT': return 'OWNER DIRECTIVE';
    case 'FINALIZING': return 'EVIDENCE FINALIZE';
    case 'BLOCKED': return 'RUNTIME BLOCKED';
    case 'READY_TO_PUBLISH': return 'DRAFT GATE READY';
    case 'COMPLETED': return 'ORDER FULFILLED // READBACK';
    case 'FAILED': return 'EXECUTION FAILED';
    case 'CANCELLED': return 'EXECUTION CANCELLED';
    default: return 'LIVING WATCH';
  }
}

export function CyborgOcularMatrix({ isTyping = false, jobPhase = 'IDLE' }: Props) {
  const rawX = useMotionValue(0);
  const rawY = useMotionValue(0);
  const x = useSpring(rawX, { stiffness: 210, damping: 24, mass: 0.45 });
  const y = useSpring(rawY, { stiffness: 210, damping: 24, mass: 0.45 });
  const pointerX = useTransform(x, [-1, 1], [-8, 8]);
  const pointerY = useTransform(y, [-1, 1], [-5, 5]);
  const reducedMotion = useReducedMotion();
  const active = ACTIVE.has(jobPhase);
  const awake = isTyping || jobPhase !== 'IDLE';
  const label = phaseLabel(isTyping && jobPhase === 'IDLE' ? 'AWAKENING' : jobPhase);

  useEffect(() => {
    const onPointer = (event: PointerEvent) => {
      rawX.set(Math.max(-1, Math.min(1, (event.clientX / Math.max(1, window.innerWidth) - 0.5) * 2)));
      rawY.set(Math.max(-1, Math.min(1, (event.clientY / Math.max(1, window.innerHeight) - 0.5) * 2)));
    };
    const center = () => { rawX.set(0); rawY.set(0); };
    window.addEventListener('pointermove', onPointer, { passive: true });
    document.documentElement.addEventListener('pointerleave', center);
    return () => {
      window.removeEventListener('pointermove', onPointer);
      document.documentElement.removeEventListener('pointerleave', center);
    };
  }, [rawX, rawY]);

  useEffect(() => { if (awake) playAwakeningSound(); }, [awake]);

  return (
    <div
      className="relative flex h-[58px] w-[126px] shrink-0 select-none items-center justify-center md:h-[66px] md:w-[146px]"
      data-testid="vnext-cyborg-ocular-matrix"
      role="img"
      aria-label={`Sovereign eye: ${label}`}
      title="EFFECTS DECORATIVE · STATE READBACK"
    >
      <motion.div
        className="absolute inset-[3px] border border-cyan-200/20 bg-black/30 [clip-path:polygon(13%_0,87%_0,100%_50%,87%_100%,13%_100%,0_50%)]"
        animate={reducedMotion ? undefined : { opacity: active ? [0.42, 0.82, 0.42] : [0.32, 0.48, 0.32] }}
        transition={{ duration: active ? 1.4 : 3.2, repeat: Infinity, ease: 'easeInOut' }}
      />
      <div className="absolute inset-x-3 top-1/2 h-px bg-gradient-to-r from-transparent via-cyan-200/55 to-transparent" />
      <div className="absolute left-1 top-1/2 font-mono text-[5px] tracking-[0.18em] text-cyan-100/45">SOV</div>
      <div className="absolute right-1 top-1/2 font-mono text-[5px] tracking-[0.18em] text-cyan-100/45">ATO</div>

      <motion.div
        className="relative h-[45px] w-[96px] overflow-hidden border border-white/45 bg-black shadow-[0_0_20px_rgba(126,231,255,0.28),inset_0_0_18px_rgba(0,0,0,0.95)] [clip-path:polygon(7%_50%,18%_17%,50%_4%,82%_17%,93%_50%,82%_83%,50%_96%,18%_83%)] md:h-[51px] md:w-[108px]"
        animate={reducedMotion ? undefined : { scaleY: [1, 1, 0.07, 1, 1] }}
        transition={{ duration: 7.2, times: [0, 0.5, 0.515, 0.535, 1], repeat: Infinity, ease: 'easeInOut' }}
      >
        <div className="absolute inset-[2px] bg-[radial-gradient(ellipse_at_center,#ffffff_0%,#f8fdff_46%,#c8d7df_72%,#56616a_100%)] [clip-path:inherit]" />
        <div className="absolute inset-x-0 top-0 h-[30%] bg-gradient-to-b from-black/35 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 h-[27%] bg-gradient-to-t from-black/28 to-transparent" />

        <motion.div
          className="absolute inset-0 flex items-center justify-center"
          animate={reducedMotion ? undefined : { x: [-4, 7, 7, -6, -4], y: [0, -2, 3, 1, 0] }}
          transition={{ duration: 8.5, times: [0, 0.24, 0.5, 0.76, 1], repeat: Infinity, ease: 'easeInOut' }}
        >
          <motion.div className="relative h-10 w-10 rounded-full" style={{ x: reducedMotion ? 0 : pointerX, y: reducedMotion ? 0 : pointerY }}>
            <div className="absolute inset-0 rounded-full border border-slate-950/70 bg-[conic-gradient(from_0deg,#07131a,#d9f9ff,#365e70,#ffffff,#173847,#bcefff,#07131a)] shadow-[0_0_12px_rgba(116,225,255,0.72),inset_0_0_10px_rgba(0,0,0,0.8)]" />
            <motion.div className="absolute inset-[4px] rounded-full border border-cyan-50/70 border-dashed" animate={reducedMotion ? undefined : { rotate: 360 }} transition={{ duration: 9, repeat: Infinity, ease: 'linear' }} />
            <motion.div className="absolute inset-[8px] rounded-full border border-slate-950/70 border-dotted" animate={reducedMotion ? undefined : { rotate: -360 }} transition={{ duration: 5.5, repeat: Infinity, ease: 'linear' }} />
            <div className="absolute inset-[11px] rounded-full bg-black ring-1 ring-cyan-100/45 shadow-[0_0_9px_rgba(0,0,0,1)]">
              <span className="absolute left-[3px] top-[3px] h-[4px] w-[4px] rounded-full bg-white shadow-[0_0_5px_white]" />
            </div>
          </motion.div>
        </motion.div>

        <motion.div
          className="absolute inset-y-0 w-px bg-cyan-100/65 shadow-[0_0_7px_rgba(165,243,252,0.9)]"
          animate={reducedMotion ? { left: '50%', opacity: 0.35 } : { left: ['14%', '86%', '14%'], opacity: active ? [0.25, 0.9, 0.25] : [0.15, 0.45, 0.15] }}
          transition={{ duration: active ? 2.2 : 4.8, repeat: Infinity, ease: 'easeInOut' }}
        />
        <div className="absolute left-1/2 top-1 h-2 w-px -translate-x-1/2 bg-cyan-200/40" />
        <div className="absolute bottom-1 left-1/2 h-2 w-px -translate-x-1/2 bg-cyan-200/40" />
        <div className="absolute left-2 top-1/2 h-px w-3 bg-cyan-200/40" />
        <div className="absolute right-2 top-1/2 h-px w-3 bg-cyan-200/40" />
      </motion.div>

      <motion.div
        className="pointer-events-none absolute inset-[7px] border border-cyan-100/10 [clip-path:polygon(10%_0,90%_0,100%_50%,90%_100%,10%_100%,0_50%)]"
        animate={reducedMotion ? undefined : { scale: active ? [0.98, 1.04, 0.98] : [1, 1.015, 1], opacity: [0.22, 0.5, 0.22] }}
        transition={{ duration: active ? 1.6 : 3.4, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  );
}
