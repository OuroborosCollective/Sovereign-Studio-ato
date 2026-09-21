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
  const x = useSpring(rawX, { stiffness: 210, damping: 24, mass: 0.42 });
  const y = useSpring(rawY, { stiffness: 210, damping: 24, mass: 0.42 });
  const eyeX = useTransform(x, [-1, 1], [-9, 9]);
  const eyeY = useTransform(y, [-1, 1], [-5, 5]);
  const rotateY = useTransform(x, [-1, 1], [-12, 12]);
  const rotateX = useTransform(y, [-1, 1], [9, -9]);

  const active = ACTIVE.has(jobPhase);
  const reducedMotion = useReducedMotion();
  const awake = isTyping || jobPhase !== 'IDLE';
  const label = phaseLabel(isTyping && jobPhase === 'IDLE' ? 'AWAKENING' : jobPhase);

  useEffect(() => {
    const onPointer = (event: PointerEvent) => {
      rawX.set(Math.max(-1, Math.min(1, (event.clientX / Math.max(1, window.innerWidth) - 0.5) * 2)));
      rawY.set(Math.max(-1, Math.min(1, (event.clientY / Math.max(1, window.innerHeight) - 0.5) * 2)));
    };
    const reset = () => { rawX.set(0); rawY.set(0); };
    window.addEventListener('pointermove', onPointer, { passive: true });
    document.documentElement.addEventListener('pointerleave', reset);
    return () => {
      window.removeEventListener('pointermove', onPointer);
      document.documentElement.removeEventListener('pointerleave', reset);
    };
  }, [rawX, rawY]);

  useEffect(() => { if (awake) playAwakeningSound(); }, [awake]);

  return (
    <div
      className="relative flex shrink-0 select-none items-center justify-center"
      data-testid="vnext-cyborg-ocular-matrix"
      role="img"
      aria-label={`Sovereign eye: ${label}`}
      title="EFFECTS DECORATIVE · STATE READBACK"
    >
      <div className="relative h-[58px] w-[118px] md:h-[68px] md:w-[142px] [perspective:850px]">
        <motion.div
          className="absolute inset-x-0 top-1/2 h-[46px] -translate-y-1/2 rounded-[50%] border border-cyan-200/20 shadow-[0_0_22px_rgba(103,232,249,0.16)]"
          animate={{ opacity: reducedMotion ? 0.35 : active ? [0.24, 0.7, 0.24] : 0.38 }}
          transition={{ duration: 1.7, repeat: active && !reducedMotion ? Infinity : 0 }}
        />
        <motion.div
          className="absolute left-1/2 top-1/2 h-[54px] w-[92px] -translate-x-1/2 -translate-y-1/2 rounded-[50%] border border-slate-300/30"
          animate={{ rotate: reducedMotion ? 0 : 360 }}
          transition={{ duration: 24, repeat: reducedMotion ? 0 : Infinity, ease: 'linear' }}
        >
          <span className="absolute -left-1 top-1/2 h-2 w-2 -translate-y-1/2 rotate-45 border border-cyan-200/60 bg-[#05080d]" />
          <span className="absolute -right-1 top-1/2 h-2 w-2 -translate-y-1/2 rotate-45 border border-cyan-200/60 bg-[#05080d]" />
        </motion.div>

        <motion.div
          className="absolute left-1/2 top-1/2 h-[44px] w-[100px] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[62%_38%_62%_38%/72%_58%_42%_28%] border border-white/55 bg-[#02050a] shadow-[0_0_20px_rgba(186,230,253,0.28),inset_0_0_18px_rgba(0,0,0,0.92)] md:h-[52px] md:w-[122px]"
          style={{ rotateX: reducedMotion ? 0 : rotateX, rotateY: reducedMotion ? 0 : rotateY, transformStyle: 'preserve-3d' }}
          animate={{ scaleY: reducedMotion ? 1 : [1, 1, 0.05, 1, 1] }}
          transition={{ duration: 7.2, times: [0, 0.47, 0.49, 0.515, 1], repeat: Infinity, ease: 'easeInOut' }}
        >
          <div className="absolute inset-[2px] overflow-hidden rounded-[inherit] bg-[radial-gradient(ellipse_at_50%_46%,#ffffff_0%,#f8fcff_48%,#cbd7df_72%,#48545f_100%)] shadow-[inset_0_5px_9px_rgba(255,255,255,0.95),inset_0_-8px_13px_rgba(3,12,20,0.48)]">
            <div className="absolute inset-x-0 top-0 h-[28%] bg-gradient-to-b from-slate-950/35 to-transparent" />
            <div className="absolute inset-x-0 bottom-0 h-[24%] bg-gradient-to-t from-slate-950/30 to-transparent" />

            <motion.div
              className="absolute left-1/2 top-1/2 -ml-[19px] -mt-[19px] h-[38px] w-[38px] rounded-full border border-cyan-100/80 bg-[repeating-conic-gradient(from_0deg,#dffaff_0deg,#4d7184_7deg,#bff6ff_13deg,#172b38_18deg)] shadow-[0_0_15px_rgba(103,232,249,0.8),inset_0_0_12px_rgba(0,0,0,0.8)] md:-ml-[22px] md:-mt-[22px] md:h-[44px] md:w-[44px]"
              style={{ x: reducedMotion ? 0 : eyeX, y: reducedMotion ? 0 : eyeY }}
              animate={{ scale: reducedMotion ? 1 : active ? [1, 1.1, 1] : 1 }}
              transition={{ duration: 1.9, repeat: active && !reducedMotion ? Infinity : 0 }}
            >
              <motion.div
                className="absolute inset-[4px] rounded-full border border-cyan-50/70 border-dashed"
                animate={{ rotate: reducedMotion ? 0 : -360 }}
                transition={{ duration: 9, repeat: reducedMotion ? 0 : Infinity, ease: 'linear' }}
              />
              <div className="absolute inset-[9px] rounded-full border border-black/60 bg-[radial-gradient(circle,#020305_0%,#020305_54%,#071b24_55%,#0b3a4a_100%)] shadow-[0_0_8px_rgba(0,0,0,0.95)]">
                <span className="absolute left-[4px] top-[3px] h-[5px] w-[5px] rounded-full bg-white shadow-[0_0_5px_white]" />
                <span className="absolute bottom-[4px] right-[4px] h-[2px] w-[2px] rounded-full bg-cyan-100" />
              </div>
            </motion.div>

            <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-cyan-300/15" />
            <div className="absolute left-0 top-1/2 h-px w-full -translate-y-1/2 bg-cyan-300/15" />
            <div className="absolute left-2 top-2 h-1 w-4 border-l border-t border-cyan-300/55" />
            <div className="absolute bottom-2 right-2 h-1 w-4 border-b border-r border-cyan-300/55" />
          </div>
        </motion.div>

        <div className="pointer-events-none absolute left-0 top-1/2 h-px w-[20px] -translate-y-1/2 bg-gradient-to-r from-transparent to-cyan-200/55" />
        <div className="pointer-events-none absolute right-0 top-1/2 h-px w-[20px] -translate-y-1/2 bg-gradient-to-l from-transparent to-cyan-200/55" />
        <div className="pointer-events-none absolute bottom-0 left-1/2 -translate-x-1/2 font-mono text-[5px] font-black tracking-[0.32em] text-cyan-100/55">SOVEREIGN // ATO</div>
      </div>
    </div>
  );
}
