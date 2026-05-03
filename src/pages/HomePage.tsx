import React, { useRef, useEffect } from 'react';
import MainLayout from '../components/layout/MainLayout';
import ErrorBoundary from '../components/common/ErrorBoundary';

/**
 * CanvasEngine
 * Kern-Engine für die generative Hintergrund-Ebene.
 * Realisiert ein dynamisches Partikel-Netzwerk mit Vektor-Interaktionen.
 */
const CanvasEngine: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) return;

    let animationFrameId: number;
    let particles: Particle[] = [];

    class Particle {
      x: number = 0;
      y: number = 0;
      vx: number = 0;
      vy: number = 0;
      radius: number = 0;

      constructor(w: number, h: number) {
        this.init(w, h);
      }

      init(w: number, h: number) {
        this.x = Math.random() * w;
        this.y = Math.random() * h;
        this.vx = (Math.random() - 0.5) * 0.6;
        this.vy = (Math.random() - 0.5) * 0.6;
        this.radius = Math.random() * 1.5 + 0.5;
      }

      update(w: number, h: number) {
        this.x += this.vx;
        this.y += this.vy;

        if (this.x < 0 || this.x > w) this.vx *= -1;
        if (this.y < 0 || this.y > h) this.vy *= -1;
      }
    }

    const init = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      particles = Array.from({ length: 120 }, () => new Particle(canvas.width, canvas.height));
    };

    const draw = () => {
      if (!ctx || !canvas) return;
      
      ctx.fillStyle = '#020617';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.lineWidth = 0.8;
      for (let i = 0; i < particles.length; i++) {
        const p1 = particles[i];
        p1.update(canvas.width, canvas.height);

        ctx.beginPath();
        ctx.arc(p1.x, p1.y, p1.radius, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(56, 189, 248, 0.5)';
        ctx.fill();

        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const dx = p1.x - p2.x;
          const dy = p1.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 150) {
            ctx.beginPath();
            ctx.strokeStyle = `rgba(56, 189, 248, ${0.15 * (1 - dist / 150)})`;
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
          }
        }
      }
      animationFrameId = requestAnimationFrame(draw);
    };

    const handleResize = () => {
      init();
    };

    window.addEventListener('resize', handleResize);
    init();
    draw();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 w-full h-full pointer-events-none"
    />
  );
};

/**
 * HomePage
 * Transformiert in einen Full-Screen Host für generative Daten-Visualisierungen.
 */
const HomePage: React.FC = () => {
  return (
    <MainLayout>
      <ErrorBoundary>
        <div className="relative min-h-[calc(100vh-64px)] w-full flex flex-col items-center justify-center overflow-hidden">
          <CanvasEngine />
          
          <div className="relative z-10 flex flex-col items-center text-center px-4">
            <div className="mb-6 px-4 py-1 border border-sky-500/30 bg-sky-500/5 rounded-full backdrop-blur-sm">
              <span className="text-sky-400 text-xs font-mono tracking-[0.3em] uppercase">
                Neural Interface Active
              </span>
            </div>

            <h1 className="text-6xl md:text-8xl font-black text-white tracking-tighter mb-4">
              SOVEREIGN<span className="text-sky-500">.</span>CORE
            </h1>
            
            <p className="max-w-2xl text-slate-400 text-lg md:text-xl font-light leading-relaxed mb-12">
              Zentrale Steuereinheit für generative Datenverarbeitung und 
              Ressourcen-Visualisierung in Echtzeit.
            </p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full max-w-4xl">
              {[
                { label: 'Analytics', val: '0x1F' },
                { label: 'Security', val: 'Active' },
                { label: 'Compute', val: '98.2%' },
                { label: 'Node', val: 'Primary' }
              ].map((stat, idx) => (
                <div key={idx} className="p-4 bg-white/5 border border-white/10 backdrop-blur-md rounded-xl group hover:border-sky-500/50 transition-colors">
                  <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1 group-hover:text-sky-400 transition-colors">
                    {stat.label}
                  </div>
                  <div className="text-xl font-mono text-white">
                    {stat.val}
                  </div>
                </div>
              ))}
            </div>

            <button className="mt-12 group relative px-10 py-4 overflow-hidden rounded-full bg-white text-slate-950 font-bold transition-all hover:scale-105 active:scale-95">
              <span className="relative z-10 uppercase tracking-widest text-sm">Initialize System Check</span>
              <div className="absolute inset-0 bg-sky-500 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
            </button>
          </div>

          <div className="absolute bottom-8 left-8 right-8 flex justify-between items-center text-[10px] font-mono text-slate-600 tracking-[0.2em] uppercase pointer-events-none">
            <div className="flex gap-4">
              <span>Latency: 12ms</span>
              <span>Buffer: Optimal</span>
            </div>
            <div>
              &copy; 2024 Sovereign Studio Design-Coder
            </div>
          </div>
        </div>
      </ErrorBoundary>
    </MainLayout>
  );
};

export default HomePage;