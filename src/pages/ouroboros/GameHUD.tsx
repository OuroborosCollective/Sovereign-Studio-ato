import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';

const SyncIndicator: React.FC = () => {
  const [syncHz, setSyncHz] = useState(10.00);

  useEffect(() => {
    const interval = setInterval(() => {
      setSyncHz(10.00 + (Math.random() - 0.5) * 0.05);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="absolute top-16 text-center">
      <div className="fira-code text-[10px] text-marina-blue font-bold tracking-widest">SYNC LCK</div>
      <div className="fira-code text-sm text-neon-green neon-string-green">{syncHz.toFixed(2)} Hz</div>
    </div>
  );
};

const GameHUD: React.FC = () => {
  return (
    <div className="relative h-screen w-full bg-matte-black overflow-hidden select-none cursor-crosshair">
      {/* Background World View Placeholder - screen (1).png */}
      <div className="absolute inset-0 bg-[url('https://lh3.googleusercontent.com/aida/ADBb0ui56DjXlSfP9g31O8-atpU4vhg2kRL8OY1-Q8L3bp8pJSqywDzP-L51eT32V5T0wqxAcaVBYSu--7Jho7GOs0TvE4mFo55eoK8gCL3YF_51ievRXHYRhFo9G3E327Q4pvUDUrbwFJ_iaaaSpY_qNv6j71hW8lkzyGloP8d8wYa6QPnE8O7zzKdYxHl7VhYuLhkNaIjCNYbCtArmEjQ50REiFCWBuAbZert06fN4Csz1dYJgI5aSyfowoHU')] bg-cover bg-center opacity-30" />

      {/* Center Crosshair */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="relative w-32 h-32 flex items-center justify-center">
          {/* Outer Ring */}
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
            className="absolute inset-0 border border-marina-blue/20 rounded-full"
          />
          {/* Inner Crosshair Lines */}
          <div className="w-12 h-[1px] bg-marina-blue shadow-[0_0_5px_#00E5FF]" />
          <div className="h-12 w-[1px] bg-marina-blue shadow-[0_0_5px_#00E5FF] absolute" />

          {/* Sync Indicator */}
          <SyncIndicator />
        </div>
      </div>

      {/* Bottom Left: Threat Radar */}
      <div className="absolute bottom-8 left-8 w-48 h-48 glass-terminal rounded-full border border-marina-blue/20 overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center">
          {/* Radar Sweep */}
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
            className="w-[200%] h-[200%] bg-gradient-to-tr from-marina-blue/20 to-transparent origin-center"
            style={{ clipPath: 'polygon(50% 50%, 100% 0, 100% 50%)' }}
          />
          {/* Grid Lines */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="w-full h-[1px] bg-marina-blue/10" />
            <div className="h-full w-[1px] bg-marina-blue/10" />
            <div className="w-3/4 h-3/4 border border-marina-blue/10 rounded-full" />
            <div className="w-1/2 h-1/2 border border-marina-blue/10 rounded-full" />
          </div>
          <span className="absolute top-2 left-1/2 -translate-x-1/2 fira-code text-[8px] text-slate-500">RADAR_THREAT_LVL_0</span>
        </div>
      </div>

      {/* Bottom Right: Combo Validator */}
      <div className="absolute bottom-8 right-8 flex flex-col items-end gap-2">
        <div className="fira-code text-[10px] text-slate-500 uppercase tracking-widest">Combo_Validator</div>
        <div className="flex gap-2">
          {[1, 1, 0, 1, 0].map((active, i) => (
            <motion.div
              key={i}
              initial={{ scale: 0.8 }}
              animate={{ scale: active ? 1 : 0.8, opacity: active ? 1 : 0.3 }}
              className={`w-6 h-6 border ${active ? 'border-neon-green neon-string-green bg-neon-green/20' : 'border-slate-700 bg-slate-900'} rotate-45`}
            />
          ))}
        </div>
        <div className="text-3xl font-black text-white italic mt-2">x4.8</div>
      </div>

      {/* Sync Animation Overlay - screen (7).png Placeholder */}
      <div className="absolute top-8 left-8 flex items-center gap-4">
        <div className="w-12 h-12 flex items-center justify-center">
           {/* Simple Wireframe Snake animation placeholder */}
           <motion.div
             animate={{ rotate: 360 }}
             transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
             className="w-8 h-8 border-t-2 border-r-2 border-marina-blue rounded-full"
           />
        </div>
        <div>
           <div className="fira-code text-xs text-marina-blue font-bold">RESONANCE_SYNCING</div>
           <div className="w-32 h-1 bg-slate-800 rounded-full mt-1 overflow-hidden">
             <motion.div
               animate={{ x: ['-100%', '100%'] }}
               transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
               className="w-1/2 h-full bg-marina-blue shadow-[0_0_10px_#00E5FF]"
             />
           </div>
        </div>
      </div>
    </div>
  );
};

export default GameHUD;
