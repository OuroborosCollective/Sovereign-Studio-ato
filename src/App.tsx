import React, { useState, useEffect, useCallback } from 'react';
import { Shield, CheckCircle, LogOut, Layout, Zap, Cpu } from 'lucide-react';

interface UserSession {
  id: string;
  email: string;
  name: string;
  imageUrl: string;
}

interface PrivacyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAccept: () => void;
}

const PrivacyModal: React.FC<PrivacyModalProps> = ({ 
  isOpen, 
  onClose, 
  onAccept 
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-stone-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full max-w-md rounded-[2rem] shadow-2xl overflow-hidden border border-stone-200 animate-in zoom-in-95 duration-300">
        <div className="p-8">
          <div className="flex items-center gap-4 mb-6">
            <div className="w-12 h-12 bg-indigo-600 rounded-2xl flex items-center justify-center text-white shadow-xl shadow-indigo-100">
              <Shield size={24} />
            </div>
            <div>
              <h2 className="text-xl font-extrabold text-stone-900 tracking-tight">Privacy Guard</h2>
              <p className="text-[10px] text-indigo-600 font-black uppercase tracking-[0.1em]">Souveräne Datenkontrolle</p>
            </div>
          </div>
          
          <div className="space-y-4 text-stone-600 text-[13px] leading-relaxed">
            <p className="font-medium">
              Deine Sicherheit ist unser Standard. Sovereign Studio arbeitet nach dem Local-First Prinzip.
            </p>
            
            <div className="space-y-3 bg-stone-50 p-5 rounded-2xl border border-stone-100">
              <div className="flex gap-3">
                <div className="mt-0.5 shrink-0">
                  <CheckCircle size={16} className="text-green-500" />
                </div>
                <span className="text-stone-700"><b>Kein Cloud-Storage:</b> Deine Keys verlassen niemals deinen lokalen Browser-Speicher.</span>
              </div>
              <div className="flex gap-3">
                <div className="mt-0.5 shrink-0">
                  <CheckCircle size={16} className="text-green-500" />
                </div>
                <span className="text-stone-700"><b>E2E Kommunikation:</b> Daten fließen ausschließlich zwischen dir und den offiziellen APIs.</span>
              </div>
              <div className="flex gap-3">
                <div className="mt-0.5 shrink-0">
                  <CheckCircle size={16} className="text-green-500" />
                </div>
                <span className="text-stone-700"><b>Full Transparency:</b> Der gesamte Quellcode ist einsehbar.</span>
              </div>
            </div>

            <p className="text-[11px] text-stone-400 italic px-2">
              Hinweis: Durch die Nutzung werden Repositories und Code-Fragmente an Google Gemini (via API) zur Analyse gesendet.
            </p>
          </div>

          <div className="mt-8 flex gap-3">
            <button 
              onClick={onClose}
              className="flex-1 px-4 py-3.5 border border-stone-200 text-stone-600 rounded-2xl font-bold text-[11px] uppercase tracking-wider hover:bg-stone-50 transition-colors"
            >
              Abbrechen
            </button>
            <button 
              onClick={onAccept}
              className="flex-1 px-4 py-3.5 bg-indigo-600 text-white rounded-2xl font-bold text-[11px] uppercase tracking-wider hover:bg-indigo-700 shadow-lg shadow-indigo-200 transition-transform active:scale-95"
            >
              Akzeptieren
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const LandingPage: React.FC<{ onLogin: () => void }> = ({ onLogin }) => (
  <div className="flex flex-col items-center justify-center min-h-screen p-6 text-center animate-in fade-in duration-500">
    <div className="w-20 h-20 bg-indigo-600 rounded-[2.5rem] flex items-center justify-center text-white mb-8 shadow-2xl shadow-indigo-200">
      <Shield size={40} />
    </div>
    <h1 className="text-4xl font-black tracking-tighter mb-4 text-stone-900">
      Sovereign Studio
    </h1>
    <p className="text-stone-500 max-w-sm mb-12 leading-relaxed">
      Deine Entwicklungsumgebung für sichere, lokale Code-Analysen und AI-Integration.
    </p>
    <button 
      onClick={onLogin}
      className="group relative flex items-center gap-4 bg-white border border-stone-200 px-8 py-4 rounded-2xl shadow-sm hover:shadow-md transition-all active:scale-95"
    >
      <img src="https://www.google.com/favicon.ico" alt="Google" className="w-5 h-5" />
      <span className="font-bold text-stone-700">Mit Google fortfahren</span>
    </button>
  </div>
);

const CanvasPage: React.FC<{ user: UserSession; onLogout: () => void; isConnected: boolean }> = ({ user, onLogout, isConnected }) => (
  <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
    <header className="p-6 border-b border-stone-200 bg-white flex justify-between items-center">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white">
          <Shield size={18} />
        </div>
        <span className="font-bold tracking-tight">Canvas View</span>
        {isConnected && (
          <div className="flex items-center gap-1.5 ml-4 px-2 py-1 bg-green-50 border border-green-100 rounded-full">
            <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
            <span className="text-[10px] font-bold text-green-700 uppercase tracking-tight">Live Connection</span>
          </div>
        )}
      </div>
      <div className="flex items-center gap-4">
        <div className="hidden sm:flex flex-col items-end">
          <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-widest leading-none mb-1">Authenticated</span>
          <span className="text-xs font-medium text-stone-500">{user.email}</span>
        </div>
        <button 
          onClick={onLogout}
          className="p-2 text-stone-400 hover:text-red-500 transition-colors"
        >
          <LogOut size={20} />
        </button>
      </div>
    </header>
    <main className="p-8">
      <div className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="col-span-2 h-[60vh] bg-white rounded-[2rem] border border-stone-200 shadow-sm p-8 flex flex-col">
          <div className="flex items-center gap-2 mb-4 text-stone-900">
            <Layout size={18} className="text-indigo-600" />
            <h3 className="text-lg font-bold">Workspace</h3>
          </div>
          <div className="flex-1 bg-stone-50 rounded-xl border border-dashed border-stone-200 flex items-center justify-center">
            <p className="text-stone-400 text-sm">Bereit für die Analyse...</p>
          </div>
        </div>
        <div className="h-[60vh] bg-stone-900 rounded-[2rem] shadow-2xl p-8 text-white overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-indigo-400">Insights</h3>
            <Zap size={18} className={isConnected ? "text-yellow-400" : "text-stone-600"} />
          </div>
          <div className="space-y-4">
            <div className="p-4 bg-stone-800 rounded-xl border border-stone-700">
              <p className="text-xs text-stone-400 mb-1 uppercase tracking-tighter">Status</p>
              <p className="text-sm font-medium">Sitzung aktiv und verschlüsselt</p>
            </div>
            <div className="p-4 bg-indigo-600/10 rounded-xl border border-indigo-500/20">
              <div className="flex items-center gap-2 mb-1">
                <Cpu size={12} className="text-indigo-300" />
                <p className="text-xs text-indigo-300 uppercase tracking-tighter">Local Node</p>
              </div>
              <p className="text-sm font-medium">Bereit für Datei-Upload</p>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
);

const App: React.FC = () => {
  const [view, setView] = useState<'landing' | 'canvas'>('landing');
  const [user, setUser] = useState<UserSession | null>(null);
  const [isPrivacyModalOpen, setIsPrivacyModalOpen] = useState(false);
  const [isCanvasConnected, setIsCanvasConnected] = useState(false);

  const establishCanvasConnection = useCallback(() => {
    console.log('Initializing AI-Canvas Connection...');
    setIsCanvasConnected(true);
  }, []);

  const handleDeepLink = useCallback((url: string) => {
    const params = new URL(url).searchParams;
    const token = params.get('token');
    const email = params.get('email');

    if (token && email) {
      const session: UserSession = {
        id: token,
        email: email,
        name: email.split('@')[0],
        imageUrl: ''
      };
      setUser(session);
      localStorage.setItem('user_session', JSON.stringify(session));
      localStorage.setItem('app_view', 'canvas');
      setView('canvas');
      establishCanvasConnection();
    }
  }, [establishCanvasConnection]);

  const initializeApp = useCallback(() => {
    const savedView = localStorage.getItem('app_view');
    const savedUser = localStorage.getItem('user_session');
    
    if (window.location.search.includes('token=')) {
      handleDeepLink(window.location.href);
      return;
    }

    if (savedView === 'canvas' && savedUser) {
      setUser(JSON.parse(savedUser));
      setView('canvas');
      establishCanvasConnection();
    } else {
      setIsPrivacyModalOpen(true);
    }
  }, [handleDeepLink, establishCanvasConnection]);

  useEffect(() => {
    initializeApp();
    
    const handleUrlChange = () => {
      if (window.location.search.includes('token=')) {
        handleDeepLink(window.location.href);
      }
    };

    window.addEventListener('popstate', handleUrlChange);
    return () => window.removeEventListener('popstate', handleUrlChange);
  }, [initializeApp, handleDeepLink]);

  const handleLogin = async () => {
    try {
      const mockResult: UserSession = { 
        id: '12345', 
        email: 'user@example.com', 
        name: 'Sovereign User',
        imageUrl: ''
      };
      
      setUser(mockResult);
      localStorage.setItem('user_session', JSON.stringify(mockResult));
      localStorage.setItem('app_view', 'canvas');
      setView('canvas');
      setIsPrivacyModalOpen(false);
      establishCanvasConnection();
    } catch (error) {
      console.error('Login error', error);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('app_view');
    localStorage.removeItem('user_session');
    setUser(null);
    setView('landing');
    setIsPrivacyModalOpen(true);
    setIsCanvasConnected(false);
  };

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 font-sans selection:bg-indigo-100">
      {view === 'landing' ? (
        <LandingPage onLogin={handleLogin} />
      ) : (
        user && <CanvasPage user={user} onLogout={handleLogout} isConnected={isCanvasConnected} />
      )}

      <PrivacyModal 
        isOpen={isPrivacyModalOpen} 
        onClose={() => setIsPrivacyModalOpen(false)} 
        onAccept={handleLogin} 
      />
    </div>
  );
};

export default App;