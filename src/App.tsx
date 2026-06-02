import React, { useEffect, useState } from 'react';
import { RefactorProvider } from './features/ai/RefactorContext';
import { RefactorPanel } from './features/ai/RefactorPanel';

/**
 * Sovereign Studio - Main Application
 * 
 * The main feature is AI-powered code refactoring.
 * All operations (repo loading, code generation, awareness) are controlled by the RefactorEngine.
 * 
 * API Keys are optional - works for free with mlvoca (no key needed).
 */

// Simple loading fallback while React initializes
function LoadingFallback() {
  return (
    <div className="min-h-screen bg-stone-950 flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-stone-400 font-mono text-sm">Loading Sovereign Studio...</p>
      </div>
    </div>
  );
}

const App: React.FC = () => {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // Small delay to ensure React is fully mounted
    const timer = setTimeout(() => {
      setIsReady(true);
    }, 100);
    return () => clearTimeout(timer);
  }, []);

  if (!isReady) {
    return <LoadingFallback />;
  }

  return (
    <RefactorProvider>
      <div className="min-h-screen bg-stone-950">
        <RefactorPanel />
      </div>
    </RefactorProvider>
  );
};

export default App;
