import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { useAppSelector } from '../../store/hooks';
import { MapPin, Box, Cpu, HardDrive } from 'lucide-react';

const WorldChunk: React.FC = () => {
  const [chunks, setChunks] = useState<any[]>([]);

  useEffect(() => {
    // Generate mock chunks
    setChunks(Array(16).fill(0).map((_, i) => ({
      id: `CHK-${1024 + i}`,
      integrity: 85 + Math.random() * 15,
      data_density: 0.4 + Math.random() * 0.6,
      locked: Math.random() > 0.8
    })));
  }, []);

  return (
    <div className="h-screen bg-matte-black text-white p-12 flex flex-col gap-8 overflow-hidden">
      <div className="flex justify-between items-start border-b border-marina-blue/10 pb-6">
        <div>
           <h1 className="text-4xl font-black tracking-tighter text-marina-blue">WORLD_CHUNK::DETECTOR</h1>
           <p className="fira-code text-xs text-slate-500 mt-2 uppercase tracking-widest">Global_Partition_v4.1</p>
        </div>
        <div className="grid grid-cols-2 gap-8 text-right">
           <div>
              <div className="text-[10px] fira-code text-slate-500">ACTIVE_SECTORS</div>
              <div className="text-marina-blue fira-code text-lg">12 / 16</div>
           </div>
           <div>
              <div className="text-[10px] fira-code text-slate-500">RES_COHERENCE</div>
              <div className="text-neon-green fira-code text-lg">0.998</div>
           </div>
        </div>
      </div>

      <div className="flex-1 grid grid-cols-4 gap-4 overflow-y-auto custom-scrollbar pr-4">
        {chunks.map((chunk) => (
          <motion.div
            key={chunk.id}
            whileHover={{ scale: 1.02, backgroundColor: 'rgba(0, 229, 255, 0.05)' }}
            className="glass-terminal p-4 border border-marina-blue/10 rounded flex flex-col gap-4 relative overflow-hidden"
          >
            {chunk.locked && (
              <div className="absolute top-0 right-0 p-2 bg-fire-red text-black fira-code text-[8px] font-bold rotate-45 translate-x-4 -translate-y-1">LOCKED</div>
            )}

            <div className="flex justify-between items-center">
               <span className="text-marina-blue fira-code text-xs">{chunk.id}</span>
               <MapPin className="w-3 h-3 text-slate-600" />
            </div>

            <div className="flex-1 flex flex-col justify-end">
               <div className="flex justify-between text-[10px] fira-code text-slate-500 mb-1">
                  <span>INTEGRITY</span>
                  <span className={chunk.integrity < 90 ? 'text-sunset-orange' : 'text-neon-green'}>{chunk.integrity.toFixed(1)}%</span>
               </div>
               <div className="w-full h-1 bg-slate-900 rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${chunk.integrity}%` }}
                    className={`h-full ${chunk.integrity < 90 ? 'bg-sunset-orange' : 'bg-neon-green'}`}
                  />
               </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
               <div className="p-1 bg-white/5 flex flex-col items-center">
                  <Box className="w-3 h-3 text-marina-blue mb-1" />
                  <span className="text-[8px] fira-code text-slate-600">OBJ</span>
               </div>
               <div className="p-1 bg-white/5 flex flex-col items-center">
                  <Cpu className="w-3 h-3 text-marina-blue mb-1" />
                  <span className="text-[8px] fira-code text-slate-600">CPU</span>
               </div>
               <div className="p-1 bg-white/5 flex flex-col items-center">
                  <HardDrive className="w-3 h-3 text-marina-blue mb-1" />
                  <span className="text-[8px] fira-code text-slate-600">MEM</span>
               </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default WorldChunk;
