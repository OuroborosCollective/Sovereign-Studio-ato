import React from 'react';
import { Shield, CheckCircle, X } from 'lucide-react';

interface PrivacyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAccept: () => void;
}

export const PrivacyModal: React.FC<PrivacyModalProps> = ({ isOpen, onClose, onAccept }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-stone-900/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl max-w-lg w-full shadow-2xl overflow-hidden border border-stone-200 flex flex-col">
        <div className="p-6 border-b border-stone-100 flex justify-between items-center">
          <div className="flex items-center gap-3 text-indigo-600">
            <Shield size={24} />
            <h2 className="text-xl font-bold text-stone-900">Datenschutz & Sicherheit</h2>
          </div>
          <button 
            onClick={onClose}
            className="text-stone-400 hover:text-stone-600 transition-colors"
          >
            <X size={20} />
          </button>
        </div>
        
        <div className="p-6 space-y-4 text-stone-600 text-sm leading-relaxed overflow-y-auto max-h-[60vh]">
          <p className="font-medium text-stone-800">
            Sovereign Studio v3 wurde mit einem &quot;Privacy First&quot; Ansatz entwickelt. Hier erfahren Sie, wie Ihre Daten verarbeitet werden:
          </p>
          
          <div className="bg-stone-50 p-4 rounded-xl border border-stone-100 space-y-3">
            <div className="flex gap-3">
              <div className="mt-1 shrink-0"><CheckCircle size={14} className="text-green-600" /></div>
              <p><strong>Lokale Speicherung:</strong> Ihre API-Keys (GitHub PAT, Gemini) werden ausschließlich verschlüsselt im <code>localStorage</code> Ihres Browsers gespeichert.</p>
            </div>
            <div className="flex gap-3">
              <div className="mt-1 shrink-0"><CheckCircle size={14} className="text-green-600" /></div>
              <p><strong>Keine Server-Backend:</strong> Diese App hat kein eigenes Backend. Alle Anfragen gehen direkt von Ihrem Browser an die offiziellen APIs von GitHub und Google.</p>
            </div>
            <div className="flex gap-3">
              <div className="mt-1 shrink-0"><CheckCircle size={14} className="text-green-600" /></div>
              <p><strong>Datenlöschung:</strong> Über die &quot;Cleanup&quot; Funktion im Header können Sie alle lokal gespeicherten sensitiven Daten mit einem Klick unwiderruflich entfernen.</p>
            </div>
          </div>

          <p>
            Durch die Nutzung von Sovereign Studio erklären Sie sich damit einverstanden, dass Ihr Code zur Analyse an die Google Gemini API übertragen wird. Es gelten die Datenschutzbestimmungen von Google Cloud.
          </p>
        </div>

        <div className="p-6 bg-stone-50 border-t border-stone-100 flex flex-col gap-3">
          <button
            onClick={onAccept}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-indigo-200 active:scale-[0.98] flex items-center justify-center gap-2"
          >
            Einverstanden & Fortfahren
          </button>
          <button
            onClick={onClose}
            className="w-full bg-white border border-stone-200 text-stone-500 font-semibold py-2 rounded-xl hover:bg-stone-100 transition-colors"
          >
            Schließen
          </button>
        </div>
      </div>
    </div>
  );
};