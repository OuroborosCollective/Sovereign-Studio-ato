import React from 'react';
import { motion } from 'motion/react';
import { Box, Code, Layers, Share2, Info } from 'lucide-react';

const AssetRepository: React.FC = () => {
  const assets = [
    { id: 'O-01', name: 'Plasma_Core_v3', type: 'Shader_Material', status: 'STABLE' },
    { id: 'O-02', name: 'Neural_Network_Grid', type: '3D_Model', status: 'STABLE' },
    { id: 'O-03', name: 'Organic_Fire_Atlas', type: 'Texture_Set', status: 'CORRUPTED' },
    { id: 'O-04', name: 'Resonance_Node', type: 'Entity_Prefab', status: 'STABLE' },
  ];

  return (
    <div className="h-screen bg-matte-black text-white flex font-ui overflow-hidden">
      {/* 3D Model Viewer Area */}
      <div className="flex-1 relative bg-black/60 flex items-center justify-center overflow-hidden border-r border-white/5">
        <div className="absolute inset-0 bg-gradient-to-t from-marina-blue/10 to-transparent pointer-events-none" />

        {/* Placeholder for Babylon.js */}
        <div className="text-center z-10">
          <Box className="w-24 h-24 text-marina-blue/20 mx-auto mb-4 animate-pulse" />
          <h2 className="fira-code text-marina-blue/40 text-xs uppercase tracking-[0.5em]">Babylon_Integration_Pending</h2>
        </div>

        {/* HUD Elements for Viewer */}
        <div className="absolute top-8 left-8 flex flex-col gap-2">
          <div className="text-[10px] fira-code text-slate-500 uppercase">Model_ID</div>
          <div className="text-marina-blue fira-code text-sm uppercase">O-01_PLASMA_CORE</div>
        </div>

        <div className="absolute bottom-8 right-8 flex gap-4">
          <button className="p-3 bg-white/5 border border-white/10 rounded-full hover:bg-marina-blue/20 hover:border-marina-blue/50 transition-all">
            <Share2 className="w-4 h-4 text-marina-blue" />
          </button>
          <button className="p-3 bg-white/5 border border-white/10 rounded-full hover:bg-marina-blue/20 hover:border-marina-blue/50 transition-all">
            <Info className="w-4 h-4 text-marina-blue" />
          </button>
        </div>
      </div>

      {/* Sidebar Metadata List */}
      <aside className="w-96 glass-terminal p-8 flex flex-col gap-8">
        <div className="border-b border-marina-blue/20 pb-4">
          <h1 className="text-2xl font-black tracking-tighter">ASSET_REPOSITORY</h1>
          <p className="fira-code text-[10px] text-slate-500 mt-1">GLOBAL_RESOURCES::SYNCED</p>
        </div>

        <div className="flex-1 flex flex-col gap-4 overflow-y-auto custom-scrollbar">
          {assets.map((asset) => (
            <motion.div
              key={asset.id}
              whileHover={{ x: 4 }}
              className="p-4 bg-white/5 border border-white/5 hover:border-marina-blue/30 transition-all cursor-pointer group"
            >
              <div className="flex justify-between items-start mb-2">
                <span className="text-[10px] fira-code text-marina-blue">{asset.id}</span>
                <span className={`text-[8px] fira-code px-1.5 py-0.5 border ${asset.status === 'STABLE' ? 'border-neon-green/50 text-neon-green' : 'border-fire-red/50 text-fire-red animate-pulse'}`}>
                  {asset.status}
                </span>
              </div>
              <h4 className="text-sm font-bold tracking-tight mb-1 group-hover:text-marina-blue transition-colors">{asset.name}</h4>
              <div className="flex items-center gap-2 text-slate-500 text-[10px] fira-code uppercase">
                <Code className="w-3 h-3" />
                {asset.type}
              </div>
            </motion.div>
          ))}
        </div>

        <div className="pt-8 border-t border-white/10">
          <div className="flex items-center justify-between mb-4">
             <span className="text-[10px] fira-code text-slate-500 uppercase">Disk_Usage</span>
             <span className="text-[10px] fira-code text-marina-blue">42.8 GB</span>
          </div>
          <div className="w-full h-1 bg-slate-800 rounded-full overflow-hidden">
             <div className="w-[42%] h-full bg-marina-blue" />
          </div>
          <button className="w-full mt-6 py-3 bg-marina-blue text-black font-bold uppercase text-xs tracking-widest hover:bg-white transition-all">
            Upload New Resource
          </button>
        </div>
      </aside>
    </div>
  );
};

export default AssetRepository;
