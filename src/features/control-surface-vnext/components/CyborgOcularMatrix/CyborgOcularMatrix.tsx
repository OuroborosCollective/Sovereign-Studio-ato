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
  const x = useSpring(rawX, { stiffness: 180, damping: 22, mass: 0.5 });
  const y = useSpring(rawY, { stiffness: 180, damping: 22, mass: 0.5 });
  const rotateY = useTransform(x, [-1, 1], [-18, 18]);
  const rotateX = useTransform(y, [-1, 1], [14, -14]);
  const irisX = useTransform(x, [-1, 1], [-8, 8]);
  const irisY = useTransform(y, [-1, 1], [-6, 6]);
  const pupilX = useTransform(x, [-1, 1], [-4, 4]);
  const pupilY = useTransform(y, [-1, 1], [-3, 3]);

  const active = ACTIVE.has(jobPhase);
  const reducedMotion = useReducedMotion();
  const awake = isTyping || jobPhase !== 'IDLE';
  const label = phaseLabel(isTyping && jobPhase === 'IDLE' ? 'AWAKENING' : jobPhase);

  useEffect(() => {
    const onPointer = (event: PointerEvent) => {
      const nx = Math.max(-1, Math.min(1, (event.clientX / Math.max(1, window.innerWidth) - 0.5) * 2));
      const ny = Math.max(-1, Math.min(1, (event.clientY / Math.max(1, window.innerHeight) - 0.5) * 2));
      rawX.set(nx);
      rawY.set(ny);
    };

    const onPointerLeave = () => {
      rawX.set(0);
      rawY.set(0);
    };

    window.addEventListener('pointermove', onPointer, { passive: true });
    document.documentElement.addEventListener('pointerleave', onPointerLeave);
    return () => {
      window.removeEventListener('pointermove', onPointer);
      document.documentElement.removeEventListener('pointerleave', onPointerLeave);
    };
  }, [rawX, rawY]);

  useEffect(() => { if (awake) playAwakeningSound(); }, [awake]);

  return (
    <div
      className="relative flex items-center justify-center select-none shrink-0"
      data-testid="vnext-cyborg-ocular-matrix"
      role="img"
      aria-label={`Sovereign eye: ${label}`}
      title="EFFECTS DECORATIVE · STATE READBACK"
    >
      <div className="relative w-[88px] h-[48px] md:w-[112px] md:h-[58px] flex items-center justify-center [perspective:700px]">
        <div className="absolute inset-x-1 top-1/2 h-px -translate-y-1/2 bg-gradient-to-r from-transparent via-cyan-200/20 to-transparent" />
        <motion.div
          className="relative w-[82px] h-[40px] md:w-[104px] md:h-[50px] overflow-hidden rounded-[58%_42%_58%_42%/68%_58%_42%_32%] border border-white/35 bg-[#05070b] shadow-[0_0_18px_rgba(185,238,255,0.15),inset_0_0_14px_rgba(0,0,0,0.9)]"
          style={{
            rotateX: reducedMotion ? 0 : rotateX,
            rotateY: reducedMotion ? 0 : rotateY,
            transformStyle: 'preserve-3d',
          }}
          animate={{ scaleY: reducedMotion ? 1 : [1, 1, 0.08, 1, 1] }}
          transition={{ duration: 6.4, times: [0, 0.46, 0.485, 0.51, 1], repeat: Infinity, ease: 'easeInOut' }}
        >
          <div className="absolute inset-[2px] overflow-hidden rounded-[inherit] border border-white/15 bg-[radial-gradient(ellipse_at_50%_42%,#ffffff_0%,#f5fbff_46%,#d4e0e8_72%,#77838d_100%)] shadow-[inset_0_3px_6px_rgba(255,255,255,0.85),inset_0_-5px_10px_rgba(12,20,28,0.42)]">
            <div className="absolute inset-x-0 top-0 h-[32%] bg-gradient-to-b from-black/20 to-transparent" />
            <div className="absolute inset-x-0 bottom-0 h-[28%] bg-gradient-to-t from-black/18 to-transparent" />

            <motion.div
              className="absolute left-1/2 top-1/2 -ml-[15px] -mt-[15px] h-[30px] w-[30px] md:-ml-[18px] md:-mt-[18px] md:h-9 md:w-9 rounded-full border border-slate-700/60 bg-[conic-gradient(from_0deg,#dff8ff,#7fa0b3,#eaffff,#60798a,#dff8ff)] shadow-[0_0_10px_rgba(176,235,255,0.48),inset_0_0_8px_rgba(6,15,22,0.72)]"
              style={{ x: reducedMotion ? 0 : irisX, y: reducedMotion ? 0 : irisY }}
              animate={{
                scale: reducedMotion ? 1 : active ? [1, 1.08, 1] : awake ? 1.03 : 1,
              }}
              transition={{ duration: 2.2, repeat: active && !reducedMotion ? Infinity : 0, ease: 'easeInOut' }}
            >
              <motion.div
                className="absolute inset-[5px] rounded-full border border-white/55 border-dashed"
                animate={{ rotate: reducedMotion ? 0 : 360 }}
                transition={{ duration: 14, repeat: reducedMotion ? 0 : Infinity, ease: 'linear' }}
              />
              <div className="absolute inset-[8px] rounded-full border border-slate-950/45" />
              <motion.div
                className="absolute left-1/2 top-1/2 -ml-[6px] -mt-[6px] h-3 w-3 md:-ml-[7px] md:-mt-[7px] md:h-[14px] md:w-[14px] rounded-full bg-black ring-1 ring-slate-900 shadow-[0_0_8px_rgba(0,0,0,0.95)]"
                style={{ x: reducedMotion ? 0 : pupilX, y: reducedMotion ? 0 : pupilY }}
              >
                <span className="absolute left-[2px] top-[2px] h-[3px] w-[3px] rounded-full bg-white shadow-[0_0_4px_rgba(255,255,255,0.95)]" />
                <span className="absolute bottom-[2px] right-[2px] h-[1.5px] w-[1.5px] rounded-full bg-cyan-100/90" />
              </motion.div>
            </motion.div>

            <div className="absolute left-2 top-1/2 h-px w-3 -translate-y-1/2 bg-cyan-300/45" />
            <div className="absolute right-2 top-1/2 h-px w-3 -translate-y-1/2 bg-cyan-300/45" />
            <div className="absolute left-1/2 top-1 h-2 w-px -translate-x-1/2 bg-cyan-300/30" />
            <div className="absolute bottom-1 left-1/2 h-2 w-px -translate-x-1/2 bg-cyan-300/30" />
          </div>

          <div className="pointer-events-none absolute inset-0 rounded-[inherit] ring-1 ring-inset ring-white/10" />
          <div className="pointer-events-none absolute left-2 top-1 font-mono text-[5px] font-black tracking-[0.18em] text-white/45">SOV</div>
          <div className="pointer-events-none absolute bottom-1 right-2 font-mono text-[5px] font-black tracking-[0.18em] text-cyan-100/45">ATO</div>
        </motion.div>

        <motion.div
          className="pointer-events-none absolute -inset-x-1 top-1/2 h-[70%] -translate-y-1/2 rounded-full border border-cyan-100/10"
          animate={{ opacity: reducedMotion ? 0.35 : active ? [0.18, 0.55, 0.18] : 0.28 }}
          transition={{ duration: 1.8, repeat: active && !reducedMotion ? Infinity : 0, ease: 'easeInOut' }}
        />
      </div>
    </div>
  );
}
