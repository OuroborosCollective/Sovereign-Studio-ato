import React from 'react';
import Header from '../navigation/Header';
import MobileNavigation from '../navigation/MobileNavigation';

interface MainLayoutProps {
  children: React.ReactNode;
}

/**
 * MainLayout: Organisiert das Layering und Hardware-Beschleunigung.
 * 
 * Layer 0 (GPU): CanvasEngine/Background - Erzwingt Layer-Promotion via will-change.
 * Layer 10 (CPU): Main Content - Standard Rendering für Text-Stabilität.
 * Layer 50 (CPU/GPU): Navigation & UI Overlays.
 */
const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  return (
    <div className="relative min-h-screen flex flex-col bg-background isolate overflow-x-hidden">
      {/* 
        GPU Layer Hint: 
        Dieser Container stellt sicher, dass Hintergrund-Elemente (z.B. CanvasEngine) 
        auf einer eigenen Composite-Layer gerendert werden.
      */}
      <div 
        className="fixed inset-0 z-0 pointer-events-none transform-gpu will-change-transform" 
        style={{ backfaceVisibility: 'hidden' }}
        aria-hidden="true"
      />

      {/* UI Layer: Header (Standard Rendering für scharfe Schriften) */}
      <header className="sticky top-0 z-50 w-full transform-none">
        <Header />
      </header>

      {/* Content Layer: Main Stacking Context */}
      <main className="relative z-10 flex-grow pb-20 lg:pb-0 outline-none transform-none">
        {children}
      </main>

      {/* UI Layer: Mobile Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 lg:hidden transform-gpu">
        <MobileNavigation />
      </nav>
    </div>
  );
};

export default MainLayout;