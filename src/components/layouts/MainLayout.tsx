import React from 'react';
import Header from '../navigation/Header';
import MobileNavigation from '../navigation/MobileNavigation';

interface MainLayoutProps {
  children: React.ReactNode;
}

const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header />
      <main className="flex-grow pb-20 lg:pb-0">
        {children}
      </main>
      <MobileNavigation />
    </div>
  );
};

export default MainLayout;