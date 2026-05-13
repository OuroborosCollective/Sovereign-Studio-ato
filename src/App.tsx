import React, { useState, useEffect } from 'react';
import AuthRoot from './pages/ouroboros/AuthRoot';
import SciencePortal from './pages/ouroboros/SciencePortal';
import ChainValidator from './pages/ouroboros/ChainValidator';
import GameHUD from './pages/ouroboros/GameHUD';
import AssetRepository from './pages/ouroboros/AssetRepository';
import { useAppSelector } from './store/hooks';

const App: React.FC = () => {
  const isRootInitialized = useAppSelector((state) => state.ouroboros.isRootInitialized);
  const [currentPage, setCurrentPage] = useState<string>('auth');

  // Handle navigation via internal state since no router is installed
  const renderPage = () => {
    switch (currentPage) {
      case 'auth':
        return <AuthRoot />;
      case 'portal':
        return <SciencePortal />;
      case 'validator':
        return <ChainValidator />;
      case 'hud':
        return <GameHUD />;
      case 'assets':
        return <AssetRepository />;
      default:
        return <AuthRoot />;
    }
  };

  useEffect(() => {
    if (isRootInitialized && currentPage === 'auth') {
      setCurrentPage('portal');
    }
  }, [isRootInitialized, currentPage]);

  return (
    <div className="relative h-screen w-full bg-matte-black text-white selection:bg-marina-blue/30 selection:text-white">
      {renderPage()}

      {/* Navigation Overlay (Only visible after root init) */}
      {isRootInitialized && (
        <nav className="fixed bottom-8 left-1/2 -translate-x-1/2 flex gap-4 px-6 py-3 glass-terminal rounded-full border border-marina-blue/20 z-50 transition-all hover:border-marina-blue/50">
          {[
            { id: 'portal', label: 'Matrix' },
            { id: 'validator', label: 'Bridge' },
            { id: 'hud', label: 'Tactical' },
            { id: 'assets', label: 'Assets' }
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setCurrentPage(item.id)}
              className={`fira-code text-[10px] uppercase tracking-widest px-3 py-1 rounded-full transition-all ${
                currentPage === item.id ? 'text-black bg-marina-blue neon-string-marina' : 'text-slate-400 hover:text-white'
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
};

export default App;
