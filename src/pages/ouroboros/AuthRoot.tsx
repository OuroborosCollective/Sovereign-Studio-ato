import React, { useState, useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '../../store/hooks';
import { initializeRoot, triggerError, clearError } from '../../features/ouroboros/ouroborosSlice';
import { motion, AnimatePresence } from 'motion/react';

const AuthRoot: React.FC = () => {
  const [hash, setHash] = useState('');
  const dispatch = useAppDispatch();
  const errorState = useAppSelector((state) => state.ouroboros.errorState);
  const isRootInitialized = useAppSelector((state) => state.ouroboros.isRootInitialized);
  const [showScanline, setShowScanline] = useState(false);

  const handleInitialize = () => {
    // Simple validation for Hex-String format
    if (/^[0-9a-fA-F]+$/.test(hash) && hash.length >= 8) {
      setShowScanline(true);
      setTimeout(() => {
        dispatch(initializeRoot(hash));
        setShowScanline(false);
      }, 2000);
    } else {
      dispatch(triggerError());
      setTimeout(() => dispatch(clearError()), 1000);
    }
  };

  return (
    <main className={`relative w-full h-screen overflow-hidden flex items-center justify-center bg-matte-black ${errorState ? 'organic-fire-glitch' : ''}`}>
      {/* Background Layer Placeholder - screen (3).png or screen (4).png */}
      <div className="absolute inset-0 bg-[url('https://lh3.googleusercontent.com/aida/ADBb0uj-byGDXcnIc5i6u9nR4vtG0p2ppgy-BtXUI781TTRB0dDFLTjnv4Xh3LkUIEjrgQwRWGiblbvxgtVU9YoaxAiAfPCgX8SUOMIe0jvP3oOyKy4hjGQFEi0ScfZ_6S4mfmzeUiJyr6WEntzcypQlJLZx1cothRSD4lQ-cNKPYxVigG8-dIOMPiIhn8HiQ9cxRDsHdIZazLOqQhCU2BYbC3mGwRV3jRnzUN7dPG1JowxlA6fxRRgmGij1EQH6')] bg-cover bg-center opacity-40 mix-blend-screen" />

      {/* Glassmorphism Terminal Window */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="relative z-10 glass-terminal p-8 rounded-lg w-full max-w-md border border-marina-blue/30 backdrop-blur-xl"
      >
        <h1 className="text-marina-blue fira-code text-xl mb-6 tracking-tighter">TERMINAL::ROOT_GATEWAY</h1>

        <div className="space-y-4">
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-widest mb-1 fira-code">kappaPos-Hash</label>
            <input
              type="text"
              value={hash}
              onChange={(e) => setHash(e.target.value)}
              placeholder="0x..."
              className="w-full bg-black/50 border border-marina-blue/20 p-3 fira-code text-neon-green focus:outline-none focus:border-marina-blue transition-colors"
            />
          </div>

          <button
            onClick={handleInitialize}
            className="w-full py-4 bg-marina-blue/10 border border-marina-blue text-marina-blue font-bold uppercase tracking-[0.2em] text-xs hover:bg-marina-blue hover:text-black transition-all neon-string-marina"
          >
            Initialize Root
          </button>
        </div>

        <div className="mt-8 flex justify-between text-[10px] fira-code text-slate-600">
          <span>DETERMINISTIC_V4.2.0</span>
          <span className="animate-pulse">WAITING_FOR_HASH...</span>
        </div>
      </motion.div>

      {/* Neon Green Scanline Effect */}
      <AnimatePresence>
        {showScanline && (
          <motion.div
            initial={{ top: '-100%' }}
            animate={{ top: '100%' }}
            exit={{ opacity: 0 }}
            transition={{ duration: 2, ease: "linear" }}
            className="absolute left-0 right-0 h-1 bg-neon-green shadow-[0_0_15px_#39FF14] z-50"
          />
        )}
      </AnimatePresence>

      {/* Status Overlay */}
      {isRootInitialized && !showScanline && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="absolute inset-0 bg-neon-green/10 flex items-center justify-center z-40 pointer-events-none"
        >
          <div className="text-neon-green fira-code text-4xl font-bold tracking-[0.5em] neon-string-green">
            ROOT_ACCESS_GRANTED
          </div>
        </motion.div>
      )}
    </main>
  );
};

export default AuthRoot;
