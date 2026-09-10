import React, { useEffect, useMemo } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'motion/react';
import type { JobPhase } from '../../types/domain';
import { playAwakeningSound } from '../../utils/audio';

interface Props { isTyping?: boolean; jobPhase?: JobPhase; }

const ACTIVE = new Set<JobPhase>(['DISPATCHING', 'PROVISIONING', 'EXECUTING', 'FINALIZING', 'READY_TO_PUBLISH']);
const BLADE_ANGLES = [0, 60, 120, 180, 240, 300];

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
  const irisX = useTransform(x, [-1, 1], [-6, 6]);
  const irisY = useTransform(y, [-1, 1], [-5, 5]);
  const pupilX = useTransform(x, [-1, 1], [-9, 9]);
  const pupilY = useTransform(y, [-1, 1], [-7, 7]);
  const active = ACTIVE.has(jobPhase);
  const ownerWait = jobPhase === 'AWAITING_OWNER_INPUT';
  const blocked = jobPhase === 'BLOCKED' || jobPhase === 'FAILED';
  const completed = jobPhase === 'COMPLETED';
  const awake = isTyping || jobPhase !== 'IDLE';
  const accent = completed ? '#10b981' : blocked || ownerWait ? '#ff8c00' : '#ff1e38';
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

  const speed = useMemo(() => active ? 1.4 : ownerWait ? 2.8 : completed ? 8 : 14, [active, ownerWait, completed]);

  return (
    <div className="relative hidden sm:flex items-center gap-2 select-none" data-testid="vnext-cyborg-ocular-matrix" aria-label={`Sovereign ocular phase ${jobPhase}`}>
      <div className="relative w-[88px] h-[48px] md:w-[112px] md:h-[58px] flex items-center justify-center overflow-visible">
        <motion.div
          className="absolute inset-[3px] rounded-[50%] border bg-black/70 shadow-[inset_0_0_28px_rgba(0,0,0,1)]"
          animate={{ borderColor: accent, boxShadow: awake ? `inset 0 0 28px rgba(0,0,0,1),0 0 22px ${accent}55` : 'inset 0 0 28px rgba(0,0,0,1),0 0 8px rgba(255,30,56,.15)' }}
        />

        <motion.div className="absolute w-[62px] h-[62px] md:w-[75px] md:h-[75px] rounded-full" animate={{ rotate: 360 }} transition={{ duration: speed * 4.2, repeat: Infinity, ease: 'linear' }}>
          {BLADE_ANGLES.map((angle) => <motion.div key={angle} className="absolute left-1/2 top-1/2 origin-[0_0]" style={{ rotate: angle }}><motion.div className="absolute -top-[2px] left-[8px] w-[21px] md:w-[27px] h-[5px] clip-path-polygon bg-gradient-to-r from-transparent to-[var(--red-pulse)]" style={{ background: `linear-gradient(90deg, transparent, ${accent})`, clipPath: 'polygon(0 40%,85% 0,100% 50%,85% 100%,0 60%)' }} animate={{ opacity: active ? [0.35, 1, 0.35] : 0.42 }} transition={{ duration: 0.75, repeat: active ? Infinity : 0, delay: angle / 520 }} /></motion.div>)}
        </motion.div>

        <motion.div className="absolute w-[48px] h-[48px] md:w-[57px] md:h-[57px] rounded-full border border-white/10" animate={{ rotate: -360, scale: active ? [1, 1.08, 1] : 1 }} transition={{ rotate: { duration: speed * 2.5, repeat: Infinity, ease: 'linear' }, scale: { duration: 0.55, repeat: active ? Infinity : 0 } }}>
          {[0, 45, 90, 135].map((a) => <span key={a} className="absolute left-1/2 top-1/2 w-[1px] h-[27px] origin-top bg-gradient-to-b from-white/25 to-transparent" style={{ transform: `rotate(${a}deg)` }} />)}
        </motion.div>

        <motion.div className="absolute w-[36px] h-[29px] md:w-[43px] md:h-[35px] rounded-[50%] border" style={{ x: irisX, y: irisY, borderColor: accent, background: `radial-gradient(circle at 50% 50%, ${accent}55 0%, #30000b 42%, #09090b 70%)`, boxShadow: `0 0 15px ${accent}88,inset 0 0 15px ${accent}55` }} animate={active ? { scale: [0.96, 1.09, 0.96], filter: ['brightness(.9)', 'brightness(1.6)', 'brightness(.9)'] } : { scale: awake ? 1 : 0.82 }} transition={{ duration: active ? 0.72 : 0.35, repeat: active ? Infinity : 0 }}>
          <motion.div className="absolute inset-[7px] md:inset-[8px] rounded-full bg-black border" style={{ x: pupilX, y: pupilY, borderColor: accent, boxShadow: `0 0 10px ${accent}` }}>
            <motion.div className="absolute left-[30%] top-[20%] w-[3px] h-[3px] rounded-full bg-white" animate={{ opacity: awake ? [0.4, 1, 0.4] : 0.25 }} transition={{ duration: 1.2, repeat: Infinity }} />
          </motion.div>
        </motion.div>

        {active && <motion.div className="absolute left-[6px] right-[6px] h-[1px]" style={{ background: accent, boxShadow: `0 0 8px ${accent}` }} animate={{ top: ['18%', '82%', '18%'], opacity: [0, 1, 0] }} transition={{ duration: 0.9, repeat: Infinity, ease: 'linear' }} />}
        {ownerWait && <motion.div className="absolute inset-0 rounded-[50%] border-2 border-dashed" style={{ borderColor: accent }} animate={{ rotate: [0, 360], scale: [1, 1.09, 1] }} transition={{ rotate: { duration: 2.6, repeat: Infinity, ease: 'linear' }, scale: { duration: 0.8, repeat: Infinity } }} />}
        {blocked && <motion.div className="absolute inset-[1px] rounded-[50%] border" style={{ borderColor: accent }} animate={{ opacity: [0.25, 1, 0.25] }} transition={{ duration: 0.45, repeat: Infinity }} />}
      </div>

      <div className="hidden lg:flex flex-col min-w-[116px] font-mono leading-tight">
        <span className="text-[7.5px] tracking-[0.18em] text-[var(--text-dim)]">OCULAR MATRIX // LIVE UI</span>
        <motion.span className="text-[9px] font-black tracking-wider" animate={{ color: accent, textShadow: awake ? `0 0 7px ${accent}66` : 'none' }}>{label}</motion.span>
        <span className="text-[7px] text-[var(--text-dim)]">EFFECTS DECORATIVE · STATE READBACK</span>
      </div>
    </div>
  );
}
