import React, { useState } from 'react';
import { motion } from 'motion/react';

const ChainValidator: React.FC = () => {
  const sourceHash = "0x5f3e22e7e3384b8b8085644911b70263";
  const [targetHash, setTargetHash] = useState("0x5f3e22e7e3384b8b8085644911b70263");

  const segments = sourceHash.split('').map((char, i) => ({
    char,
    mismatch: targetHash[i] !== char
  }));

  return (
    <div className="h-screen bg-matte-black text-white p-12 flex flex-col gap-8">
      {/* Header */}
      <div className="flex justify-between items-end border-b border-marina-blue/20 pb-4">
        <div>
          <h1 className="text-4xl font-black tracking-tighter text-marina-blue">CHAIN-STRING::VALIDATOR</h1>
          <p className="text-slate-500 fira-code text-xs mt-2 uppercase tracking-widest">Security_Bridge_Layer_v0.1</p>
        </div>
        <div className="text-right">
          <div className="text-xs fira-code text-marina-blue neon-string-marina px-3 py-1 border border-marina-blue">BRIDGE_STATUS: STABLE</div>
        </div>
      </div>

      {/* Hex Dumps */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 flex-1">
        <div className="glass-terminal p-8 rounded-lg flex flex-col gap-6">
          <h3 className="fira-code text-xs text-slate-500 uppercase tracking-[0.3em]">Source_Payload</h3>
          <div className="text-4xl fira-code break-all leading-relaxed text-slate-400">
            {sourceHash.split('').map((char, i) => (
              <span key={i} className="hover:text-marina-blue transition-colors cursor-default">{char}</span>
            ))}
          </div>
        </div>

        <div className="glass-terminal p-8 rounded-lg flex flex-col gap-6 relative overflow-hidden">
           {/* Background Layer Placeholder - screen (6).png */}
           <div className="absolute inset-0 bg-[url('https://lh3.googleusercontent.com/aida/ADBb0uiHRQzajx7H_CKLL95v_svb_ACmOeP_K4pTYQUvNzfQ7rCUB6VBQ0l785FcD-mUWzcmBiHQwVIX8ya9qRjBvaKn3WcpDXw2ax3pQElMVKSob6otIJjvuUxo4z_RHAIx7zkPe5Byw0hxRGtuJgMbhGoZZ4yPYcEeQ7kMcrpmaerb8XaBYPHdKE8efnqLts0AyOllu1rW8gw8-GdMoemhgO9Bxi64H42GT-wqwPB6MblqlSZR_2myefmmxJmM')] bg-cover opacity-5 pointer-events-none" />

          <h3 className="fira-code text-xs text-slate-500 uppercase tracking-[0.3em]">Target_Validator</h3>
          <div className="text-4xl fira-code break-all leading-relaxed">
            {segments.map((seg, i) => (
              <span
                key={i}
                className={seg.mismatch ? "text-fire-red animate-pulse organic-fire-glow" : "text-neon-green"}
                onClick={() => {
                  const newHash = targetHash.split('');
                  newHash[i] = newHash[i] === 'f' ? '0' : String.fromCharCode(newHash[i].charCodeAt(0) + 1);
                  setTargetHash(newHash.join(''));
                }}
              >
                {targetHash[i] || ' '}
              </span>
            ))}
          </div>
          <div className="mt-auto pt-8 border-t border-white/5">
            <button
              className="px-6 py-2 border border-marina-blue/30 text-marina-blue fira-code text-[10px] uppercase tracking-widest hover:bg-marina-blue/10 transition-all"
              onClick={() => setTargetHash(sourceHash)}
            >
              Force_Resync_Chain
            </button>
          </div>
        </div>
      </div>

      {/* Terminal Footer */}
      <div className="h-48 glass-terminal p-6 rounded-lg border border-marina-blue/10 flex flex-col gap-4">
        <div className="flex justify-between items-center text-[10px] fira-code text-slate-500 uppercase tracking-widest">
           <span>Sub_Process_v2</span>
           <span>0x000FF32</span>
        </div>
        <div className="flex-1 overflow-y-auto fira-code text-xs text-marina-blue/60 custom-scrollbar">
           <div>VALIDATING_BLOCK_0xFA... OK</div>
           <div>VALIDATING_BLOCK_0xFB... OK</div>
           <div className="text-fire-red">[!] MISMATCH_DETECTED_AT_INDEX_12</div>
           <div>INITIATING_RECOVERY_PROTOCOL...</div>
           <div className="text-neon-green">SUCCESS: STRING_ROOT_ESTABLISHED</div>
        </div>
      </div>
    </div>
  );
};

export default ChainValidator;
