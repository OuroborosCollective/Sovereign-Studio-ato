import React from 'react';
import Header from '../navigation/Header';
import MobileNavigation from '../navigation/MobileNavigation';

interface MainLayoutProps {
  children: React.ReactNode;
}

/**
 * MainLayout: Organisiert das Z-Index Layering der Applikation.
 * Layer 0: CanvasEngine (Background, via CSS/Component z-0)
 * Layer 10: Main Content (Inhaltsebene)
 * Layer 50: Navigation & Overlays (UI-Ebene)
 */
const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  return (
    <div className="relative min-h-screen flex flex-col bg-background isolate overflow-x-hidden">
      {/* Navigation Overlay Layer - Top */}
      <header className="sticky top-0 z-50 w-full">
        <Header />
      </header>

      {/* Main Content Layer - Central Stacking */}
      <main className="relative z-10 flex-grow pb-20 lg:pb-0 outline-none">
        {children}
      </main>

      {/* Mobile Navigation Layer - Bottom Overlay */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 lg:hidden">
        <MobileNavigation />
      </nav>
    </div>
  );
};

export default MainLayout;