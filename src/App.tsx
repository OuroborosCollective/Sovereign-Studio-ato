import React from 'react';
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

const App: React.FC = () => {
  return (
    <RefactorProvider>
      <div className="min-h-screen bg-stone-950">
        <RefactorPanel />
      </div>
    </RefactorProvider>
  );
};

export default App;
