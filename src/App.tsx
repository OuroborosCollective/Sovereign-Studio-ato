import React, { useState } from 'react';
import { Shield, CheckCircle } from 'lucide-react';

interface PrivacyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAccept: () => void;
}

export const PrivacyModal: React.FC<PrivacyModalProps> = ({ 
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
                <span className="text-stone-700"><b>Full Transparency:</b> Der gesamte Quellcode der Analyse-Tools ist einsehbar.</span>
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

const App: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(true);

  return (
    <div className="min-h-screen bg-stone-50">
      <PrivacyModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onAccept={() => setIsModalOpen(false)} 
      />
    </div>
  );
};

export default App;