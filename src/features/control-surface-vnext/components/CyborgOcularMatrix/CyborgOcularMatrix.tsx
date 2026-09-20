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
  const pupilX = useTransform(x, [-1, 1], [-9, 9]);
  const pupilY = useTransform(y, [-1, 1], [-7, 7]);
  const active = ACTIVE.has(jobPhase);
  const reducedMotion = useReducedMotion();
  const awake = isTyping || jobPhase !== 'IDLE';
  const label = phaseLabel(isTyping && jobPhase === 'IDLE' ? 'AWAKENING' : jobPhase);

  useEffect(() => {
    const onPointer = (event: PointerEvent) => {
      const nx = Math.max(-1, Math.min(1, (event.clientX / Math.max(1, window.innerWidth) - 0.5) * 2));
      const ny = Math.max(-1, Math.min(1, (event.clientY / Math.max(1, window.innerHeight) - 0.5) * 2));
      rawX.set(nx); rawY.set(ny);
    };
    window.addEventListener('pointermove', onPointer, { passive: true });
    return () => window.removeEventListener('pointermove', onPointer);
  }, [rawX, rawY]);

  useEffect(() => { if (awake) playAwakeningSound(); }, [awake]);

  return (
    <div className="relative flex items-center justify-center select-none shrink-0" data-testid="vnext-cyborg-ocular-matrix" role="img" aria-label={`Sovereign eye: ${label}`} title="EFFECTS DECORATIVE · STATE READBACK">
      <div className="relative w-[88px] h-[48px] md:w-[112px] md:h-[58px] flex items-center justify-center">
        <motion.div
          className="relative w-[78px] h-[36px] md:w-[100px] md:h-[46px] overflow-hidden border border-white/80 bg-white shadow-[0_0_16px_rgba(255,255,255,0.16),inset_0_-4px_8px_rgba(0,0,0,0.12)]"
          style={{ borderRadius: '70% 30% 70% 30% / 60% 40% 60% 40%' }}
          animate={{ scaleY: reducedMotion ? 1 : [1, 1, 0.06, 1, 1] }}
          transition={{ duration: 6, times: [0, 0.44, 0.465, 0.49, 1], repeat: Infinity, ease: 'easeInOut' }}
        >
          <motion.div
            className="absolute left-1/2 top-1/2 -ml-3 -mt-3 h-6 w-6 md:-ml-3.5 md:-mt-3.5 md:h-7 md:w-7 rounded-full bg-black ring-[3px] ring-neutral-300"
            style={{ x: reducedMotion ? 0 : pupilX, y: reducedMotion ? 0 : pupilY }}
            animate={{ scale: reducedMotion ? 1 : active ? [1, 1.08, 1] : awake ? 1.06 : 1 }}
            transition={{ duration: 2.4, repeat: active && !reducedMotion ? Infinity : 0, ease: 'easeInOut' }}
          >
            <span className="absolute left-1.5 top-1 w-1.5 h-1.5 rounded-full bg-white" />
            <span className="absolute bottom-1.5 right-1.5 w-0.5 h-0.5 rounded-full bg-white/60" />
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
}
