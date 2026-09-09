// Biomodular Cybernetic Web Audio Synthesizer. These sounds are decorative only and never represent runtime truth.
let audioCtx: AudioContext | null = null;
let isMuted = false;

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (AudioContextClass) audioCtx = new AudioContextClass();
  }
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  return audioCtx;
}
export function toggleAudioMute(): boolean { isMuted = !isMuted; return isMuted; }
export function getAudioMuted(): boolean { return isMuted; }

export function playAwakeningSound() {
  if (isMuted) return;
  const ctx = getAudioContext(); if (!ctx) return;
  try {
    const now = ctx.currentTime; const osc = ctx.createOscillator(); const gain = ctx.createGain();
    osc.type = 'sawtooth'; osc.frequency.setValueAtTime(140, now); osc.frequency.exponentialRampToValueAtTime(480, now + 0.15); osc.frequency.exponentialRampToValueAtTime(320, now + 0.3);
    gain.gain.setValueAtTime(0.001, now); gain.gain.linearRampToValueAtTime(0.04, now + 0.05); gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);
    osc.connect(gain); gain.connect(ctx.destination); osc.start(now); osc.stop(now + 0.35);
  } catch { /* browser audio may be restricted */ }
}

let lastChirpTime = 0;
export function playKeystrokeChirp() {
  if (isMuted) return;
  const nowMs = Date.now(); if (nowMs - lastChirpTime < 80) return; lastChirpTime = nowMs;
  const ctx = getAudioContext(); if (!ctx) return;
  try {
    const now = ctx.currentTime; const osc = ctx.createOscillator(); const gain = ctx.createGain();
    osc.type = 'triangle'; osc.frequency.setValueAtTime(1200 + Math.random() * 400, now); osc.frequency.exponentialRampToValueAtTime(600, now + 0.03);
    gain.gain.setValueAtTime(0.015, now); gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.03);
    osc.connect(gain); gain.connect(ctx.destination); osc.start(now); osc.stop(now + 0.03);
  } catch { /* decorative audio only */ }
}

export function playDispatchBlast() {
  if (isMuted) return;
  const ctx = getAudioContext(); if (!ctx) return;
  try {
    const now = ctx.currentTime;
    const subOsc = ctx.createOscillator(); const subGain = ctx.createGain(); subOsc.type = 'sine'; subOsc.frequency.setValueAtTime(160, now); subOsc.frequency.exponentialRampToValueAtTime(45, now + 0.4); subGain.gain.setValueAtTime(0.08, now); subGain.gain.exponentialRampToValueAtTime(0.001, now + 0.45); subOsc.connect(subGain); subGain.connect(ctx.destination); subOsc.start(now); subOsc.stop(now + 0.45);
    const pingOsc = ctx.createOscillator(); const pingGain = ctx.createGain(); pingOsc.type = 'sawtooth'; pingOsc.frequency.setValueAtTime(880, now); pingOsc.frequency.exponentialRampToValueAtTime(220, now + 0.25); pingGain.gain.setValueAtTime(0.03, now); pingGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.25); pingOsc.connect(pingGain); pingGain.connect(ctx.destination); pingOsc.start(now); pingOsc.stop(now + 0.25);
  } catch { /* decorative audio only */ }
}

export function playVerificationChime() {
  if (isMuted) return;
  const ctx = getAudioContext(); if (!ctx) return;
  try {
    const now = ctx.currentTime;
    [523.25, 659.25, 783.99, 1046.5].forEach((freq, idx) => {
      const osc = ctx.createOscillator(); const gain = ctx.createGain(); const noteStart = now + idx * 0.08;
      osc.type = 'sine'; osc.frequency.setValueAtTime(freq, noteStart); gain.gain.setValueAtTime(0.001, noteStart); gain.gain.linearRampToValueAtTime(0.03, noteStart + 0.02); gain.gain.exponentialRampToValueAtTime(0.0001, noteStart + 0.3); osc.connect(gain); gain.connect(ctx.destination); osc.start(noteStart); osc.stop(noteStart + 0.3);
    });
  } catch { /* decorative audio only */ }
}
