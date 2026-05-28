import React, { useRef, useEffect } from 'react';
import MainLayout from '../components/layouts/MainLayout';
import { ErrorBoundary } from '../components/ErrorBoundary';

/**
 * CanvasEngine
 * Hochperformante Partikel-Simulation für den systemweiten Hintergrund.
 */
const CanvasEngine: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouseRef = useRef({ x: 0, y: 0, active: false });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) return;

    let animationFrameId: number;
    let particles: Particle[] = [];
    const particleCount = 150;
    const connectionDistance = 160;

    class Particle {
      x: number = 0;
      y: number = 0;
      vx: number = 0;
      vy: number = 0;
      radius: number = 0;

      constructor(w: number, h: number) {
        this.reset(w, h);
      }

      reset(w: number, h: number) {
        this.x = Math.random() * w;
        this.y = Math.random() * h;
        this.vx = (Math.random() - 0.5) * 0.4;
        this.vy = (Math.random() - 0.5) * 0.4;
        this.radius = Math.random() * 1.2 + 0.8;
      }

      update(w: number, h: number) {
        this.x += this.vx;
        this.y += this.vy;

        if (this.x < 0) this.x = w;
        if (this.x > w) this.x = 0;
        if (this.y < 0) this.y = h;
        if (this.y > h) this.y = 0;

        if (mouseRef.current.active) {
          const dx = mouseRef.current.x - this.x;
          const dy = mouseRef.current.y - this.y;
          // ⚡ Bolt: Optimize with squared distance to avoid expensive Math.sqrt calls
          const distSq = dx * dx + dy * dy;
          if (distSq < 40000) { // 200 * 200
            this.vx -= dx * 0.0001;
            this.vy -= dy * 0.0001;
          }
        }
      }
    }

    const init = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      particles = Array.from({ length: particleCount }, () => new Particle(canvas.width, canvas.height));
    };

    const draw = () => {
      if (!ctx || !canvas) return;

      ctx.fillStyle = '#020617';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.lineWidth = 0.6;
      const connectionDistanceSq = connectionDistance * connectionDistance;

      for (let i = 0; i < particles.length; i++) {
        const p1 = particles[i];
        p1.update(canvas.width, canvas.height);

        ctx.beginPath();
        ctx.arc(p1.x, p1.y, p1.radius, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(56, 189, 248, 0.4)';
        ctx.fill();

        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const dx = p1.x - p2.x;
          const dy = p1.y - p2.y;
          // ⚡ Bolt: Optimize with squared distance, only calculate Math.sqrt if within range
          const distSq = dx * dx + dy * dy;

          if (distSq < connectionDistanceSq) {
            const dist = Math.sqrt(distSq);
            const alpha = 0.2 * (1 - dist / connectionDistance);
            ctx.beginPath();
            ctx.strokeStyle = `rgba(56, 189, 248, ${alpha})`;
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
          }
        }
      }
      animationFrameId = requestAnimationFrame(draw);
    };

    const handleResize = () => init();
    const handleMouseMove = (e: MouseEvent) => {
      mouseRef.current = { x: e.clientX, y: e.clientY, active: true };
    };
    const handleMouseLeave = () => {
      mouseRef.current.active = false;
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseleave', handleMouseLeave);

    init();
    draw();

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
      canvas.removeEventListener('mouseleave', handleMouseLeave);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 z-0 bg-slate-950"
    />
  );
};

/**
 * HomePage
 * Fullscreen Interface Transformation.
 */
import { useState } from 'react';

const HomePage: React.FC = () => {
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [activeTab, setActiveTab] = useState<'explorer' | 'editor' | 'chat'>('explorer');

  return (
    <MainLayout
      headerProps={{
        loadingTree: false,
        setShowPrivacy,
        handleCleanup: () => {},
        fetchRepoTree: () => {}
      }}
      mobileNavProps={{
        activeTab,
        setActiveTab
      }}
    >
      <ErrorBoundary>
        <main className="relative w-full h-screen overflow-hidden flex items-center justify-center">
          <CanvasEngine />

          {/* System HUD Overlay */}
          <div className="absolute inset-0 z-10 flex flex-col justify-between p-8 pointer-events-none">
            {/* Top Bar */}
            <div className="flex justify-between items-start">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-sky-500 animate-pulse" />
                  <span className="text-sky-500 font-mono text-xs tracking-widest uppercase">System Online</span>
                </div>
                <span className="text-slate-500 font-mono text-[10px]">SVRGN_CORE_V4.2.0</span>
              </div>
              <div className="text-right">
                <div className="text-white font-mono text-xl">10:42:04</div>
                <div className="text-slate-500 font-mono text-[10px] uppercase">Zentralzeit-Referenz</div>
              </div>
            </div>

            {/* Central Control Unit */}
            <div className="flex flex-col items-center pointer-events-auto">
              <div className="mb-8 p-4 border border-white/5 bg-slate-950/40 backdrop-blur-xl rounded-2xl flex flex-col items-center max-w-lg text-center">
                <h1 className="text-5xl md:text-7xl font-black text-white tracking-tight mb-2">
                  CORE<span className="text-sky-500">.</span>INTERFACE
                </h1>
                <p className="text-slate-400 font-light text-sm md:text-base leading-relaxed">
                  Generative Datenströme werden in Echtzeit synchronisiert. 
                  Sovereign Studio Design-Coder initiiert Protokoll-Layer.
                </p>
                
                <div className="mt-8 flex gap-4">
                  <button className="px-8 py-3 bg-white text-slate-950 font-bold text-xs uppercase tracking-widest rounded-full hover:bg-sky-500 hover:text-white transition-all transform hover:scale-105 active:scale-95">
                    Start Protocol
                  </button>
                  <button className="px-8 py-3 border border-white/10 bg-white/5 text-white font-bold text-xs uppercase tracking-widest rounded-full hover:bg-white/10 transition-all backdrop-blur-sm">
                    Analyze
                  </button>
                </div>
              </div>

              {/* Live Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full max-w-4xl">
                {[
                  { label: 'Uplink', val: 'Active', unit: 'Stable' },
                  { label: 'Neural', val: '84.2', unit: 'GFLOPS' },
                  { label: 'Latency', val: '12', unit: 'ms' },
                  { label: 'Load', val: '14', unit: '%' }
                ].map((stat, i) => (
                  <div key={i} className="p-4 bg-slate-950/40 border border-white/5 backdrop-blur-md rounded-xl hover:border-sky-500/30 transition-colors">
                    <div className="text-[9px] uppercase tracking-tighter text-slate-500">{stat.label}</div>
                    <div className="flex items-baseline gap-1">
                      <span className="text-lg font-mono text-white">{stat.val}</span>
                      <span className="text-[9px] font-mono text-sky-500/70">{stat.unit}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Footer Bar */}
            <div className="flex justify-between items-end text-slate-600 font-mono text-[9px] uppercase tracking-widest">
              <div className="flex gap-8">
                <div className="flex flex-col">
                  <span>Memory Sector</span>
                  <span className="text-slate-400">0x004F32A</span>
                </div>
                <div className="flex flex-col">
                  <span>Encryption</span>
                  <span className="text-slate-400">AES-256-GCM</span>
                </div>
              </div>
              <div>
                &copy; 2024 SOVEREIGN STUDIO DESIGN-CODER
              </div>
            </div>
          </div>
        </main>
      </ErrorBoundary>
    </MainLayout>
  );
};

export default HomePage;