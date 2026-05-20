import React, { useEffect, useState, useRef } from 'react';
import { useAppSelector } from '../../store/hooks';
import { motion } from 'motion/react';
import { Activity, Shield, Zap, Database, Terminal, LayoutDashboard, Cpu } from 'lucide-react';

const Sparkline: React.FC<{ color: string, res: number }> = ({ color, res }) => {
  const [points, setPoints] = useState<number[]>(Array(20).fill(50));

  useEffect(() => {
    const interval = setInterval(() => {
      setPoints(prev => {
        const next = [...prev.slice(1), 30 + Math.sin(Date.now() * 0.01 * res) * 20 + Math.random() * 10];
        return next;
      });
    }, 100);
    return () => clearInterval(interval);
  }, [res]);

  const path = points.map((p, i) => `${i * 6},${p}`).join(' L ');

  return (
    <svg width="120" height="60" className="overflow-visible">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        points={`M ${path}`}
        className="transition-all duration-100"
      />
    </svg>
  );
};

const NeuralGrid: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let frame = 0;
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = 'rgba(0, 229, 255, 0.1)';
      ctx.lineWidth = 1;

      const size = 30;
      for (let x = 0; x < canvas.width; x += size) {
        for (let y = 0; y < canvas.height; y += size) {
          const noise = Math.sin(x * 0.01 + y * 0.01 + frame * 0.05);
          if (noise > 0.8) {
            ctx.fillStyle = `rgba(57, 255, 20, ${noise - 0.5})`;
            ctx.fillRect(x, y, 2, 2);
          }
          ctx.strokeRect(x, y, size, size);
        }
      }
      frame++;
      requestAnimationFrame(draw);
    };
    draw();
  }, []);

  return <canvas ref={canvasRef} width={800} height={400} className="w-full h-full opacity-30" />;
};

const MatrixStream: React.FC = () => {
  const [matrixData, setMatrixData] = useState<string[]>([]);

  useEffect(() => {
    const interval = setInterval(() => {
      setMatrixData(prev => {
        const line = Array(40).fill(0).map(() => Math.random() > 0.5 ? '1' : '0').join('');
        return [line, ...prev.slice(0, 15)];
      });
    }, 200);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex-1 fira-code text-[10px] text-marina-blue/20 leading-none break-all overflow-hidden select-none">
      {matrixData.map((line, i) => (
        <div key={i} className="mb-1">{line}</div>
      ))}
    </div>
  );
};

const SciencePortal: React.FC = () => {
  const telemetry = useAppSelector((state) => state.ouroboros.telemetry);
  const resonance = useAppSelector((state) => state.ouroboros.resonance);

  return (
    <div className="flex h-screen bg-matte-black text-white font-ui overflow-hidden">
      {/* Sidebar */}
      <aside className="w-16 border-r border-marina-blue/10 flex flex-col items-center py-8 gap-8 bg-black/40 backdrop-blur-md z-20">
        <LayoutDashboard className="text-marina-blue w-6 h-6" />
        <Database className="text-slate-600 hover:text-marina-blue transition-colors cursor-pointer w-5 h-5" />
        <Activity className="text-slate-600 hover:text-marina-blue transition-colors cursor-pointer w-5 h-5" />
        <Zap className="text-slate-600 hover:text-marina-blue transition-colors cursor-pointer w-5 h-5" />
        <div className="mt-auto">
          <Terminal className="text-slate-600 w-5 h-5" />
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col relative">
        {/* Top Bar */}
        <header className="h-16 border-b border-marina-blue/10 flex items-center justify-between px-8 bg-black/20 backdrop-blur-md z-10">
          <div className="flex gap-12">
            <div className="flex flex-col">
              <span className="text-[10px] text-slate-500 uppercase tracking-widest fira-code">SYS_LOAD</span>
              <span className="text-marina-blue fira-code text-sm font-bold">{telemetry.sysLoad}%</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] text-slate-500 uppercase tracking-widest fira-code">RES_SYNC</span>
              <span className="text-neon-green fira-code text-sm font-bold">{telemetry.resSync.toFixed(2)} Hz</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-[10px] text-slate-500 uppercase tracking-widest fira-code">Uplink_Status</div>
              <div className="text-marina-blue fira-code text-xs animate-pulse">{telemetry.uplinkStatus}</div>
            </div>
            <div className="w-8 h-8 rounded-full border border-marina-blue/50 flex items-center justify-center">
              <Shield className="w-4 h-4 text-marina-blue" />
            </div>
          </div>
        </header>

        {/* Dashboard Grid */}
        <div className="flex-1 p-8 grid grid-cols-12 gap-6 overflow-y-auto relative custom-scrollbar">
          {/* Widgets */}
          <motion.div
            className="col-span-12 lg:col-span-4 glass-terminal p-6 rounded-lg border border-marina-blue/20 relative overflow-hidden resonance-pulse"
          >
            <div className="flex justify-between items-start mb-4">
              <h3 className="fira-code text-marina-blue text-xs uppercase tracking-widest">ARE-Trader</h3>
              <Sparkline color="#00E5FF" res={resonance} />
            </div>
            <div className="text-2xl font-bold fira-code text-white mb-2">Ξ 1,420.69</div>
            <div className="text-[10px] text-neon-green fira-code uppercase tracking-wider">+4.2% RES_STABLE</div>
          </motion.div>

          <motion.div
            className="col-span-12 lg:col-span-4 glass-terminal p-6 rounded-lg border border-marina-blue/20 resonance-pulse"
            style={{ animationDelay: '0.5s' } as any}
          >
            <div className="flex justify-between items-start mb-4">
              <h3 className="fira-code text-marina-blue text-xs uppercase tracking-widest">Health-Decay</h3>
              <Sparkline color="#39FF14" res={resonance * 1.5} />
            </div>
            <div className="text-2xl font-bold fira-code text-white mb-2">99.98%</div>
            <div className="text-[10px] text-slate-500 fira-code uppercase tracking-wider">CELLULAR_INTEGRITY_OPTIMAL</div>
          </motion.div>

          {/* Dynamic Matrix Data Stream + Neural Grid */}
          <div className="col-span-12 lg:col-span-8 h-[400px] glass-terminal rounded-lg border border-marina-blue/10 flex flex-col relative overflow-hidden">
             <div className="absolute inset-0 z-0">
                <NeuralGrid />
             </div>
             <div className="relative z-10 p-4 flex flex-col h-full">
                <div className="text-[10px] fira-code text-marina-blue/40 uppercase tracking-widest mb-4">Matrix_Stream_Output</div>
                <MatrixStream />
             </div>
             <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black/80 pointer-events-none" />
          </div>

          <div className="col-span-12 lg:col-span-4 h-[400px] glass-terminal rounded-lg border border-marina-blue/10 p-6 flex flex-col">
            <h3 className="fira-code text-slate-500 text-xs uppercase tracking-widest mb-4">Real-time Logs</h3>
            <div className="flex-1 overflow-y-auto space-y-2 fira-code text-[10px] text-slate-400 custom-scrollbar">
               <div>[02:45:21] {">>"} INIT_PROTOCOL_LAYER</div>
               <div className="text-marina-blue">[02:45:22] {">>"} SYNC_RES_WAVE_0.842</div>
               <div>[02:45:23] {">>"} ARE_PAYLOAD_VALIDATED</div>
               <div className="text-sunset-orange">[02:45:24] {">>"} WARN_LATENCY_SPIKE_12ms</div>
               <div>[02:45:25] {">>"} ROOT_GATE_READY</div>
               <div className="text-neon-green">[02:45:26] {">>"} NEURAL_GRID_ACTIVE</div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default SciencePortal;
