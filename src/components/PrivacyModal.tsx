import React from 'react';
import { Shield } from 'lucide-react';

interface PrivacyModalProps {
  show: boolean;
  onClose: () => void;
}

export function PrivacyModal({ show, onClose }: PrivacyModalProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-stone-900/60 z-[110] flex items-center justify-center p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6 text-left border border-stone-200 animate-in zoom-in-95 duration-200 flex flex-col max-h-[80vh]">
        <div className="flex items-center gap-3 mb-4 border-b border-stone-100 pb-3">
          <div className="w-10 h-10 bg-stone-100 text-stone-600 rounded-full flex items-center justify-center shadow-sm shrink-0 transform hover:scale-110 transition-transform cursor-help">
            <Shield size={20} />
          </div>
          <h2 className="text-lg font-black text-stone-800 tracking-tight">Datenschutz & EULA (EU DSGVO)</h2>
        </div>
        
        <div className="overflow-y-auto custom-scrollbar pr-2 space-y-4 text-xs text-stone-700 leading-relaxed flex-1">
          <section className="group hover:bg-stone-50 p-2 rounded-lg transition-colors">
            <h3 className="font-bold text-stone-900 text-sm mb-1 group-hover:text-indigo-700 transition-colors">1. Lokale Speicherung (Preferences) & DSGVO</h3>
            <p>Die App speichert API-Schlüssel (GitHub PAT, Gemini API Key) <b>ausschließlich lokal</b> (über Capacitor Preferences oder lokalen App-Speicher). In Übereinstimmung mit der DSGVO weisen wir darauf hin, dass wir diese Schlüssel zu keinem Zeitpunkt unserer eigenen Infrastruktur zugänglich machen.</p>
          </section>
          
          <section className="group hover:bg-stone-50 p-2 rounded-lg transition-colors">
            <h3 className="font-bold text-stone-900 text-sm mb-1 group-hover:text-indigo-700 transition-colors">2. Externe Dienstanbieter</h3>
            <p>Die App kommuniziert zur Erfüllung ihrer Funktion über sichere (HTTPS) Protokolle mit:</p>
            <ul className="list-disc pl-5 mt-1 space-y-1">
              <li><b>GitHub Inc.</b> (api.github.com) – Git-Repository-Verarbeitung.</li>
              <li><b>Google Ireland Ltd.</b> (Generative AI) – KI-Unterstützung.</li>
              <li><b>PostHog</b> (EU Server) – Aggregierte, anonymisierte Nutzungsstatistiken ohne PII (Personally Identifiable Information).</li>
            </ul>
          </section>

          <section className="group hover:bg-stone-50 p-2 rounded-lg transition-colors">
            <h3 className="font-bold text-stone-900 text-sm mb-1 group-hover:text-indigo-700 transition-colors">3. Rechte der Betroffenen (DSGVO Art. 15-21)</h3>
            <p>Da wir initial keine Kontodaten von Ihnen speichern, müssen Sie zur Löschung (Art. 17) der rein lokalen Daten den In-App "CLEANUP"-Button verwenden oder Ihren App-Datenspeicher leeren. Anonymisiertes Analytics-Tracking bedarf gemäß gängiger Praxis Ihrer expliziten Zustimmung.</p>
          </section>
          
          <section className="group hover:bg-stone-50 p-2 rounded-lg transition-colors">
            <h3 className="font-bold text-stone-900 text-sm mb-1 group-hover:text-indigo-700 transition-colors">4. Impressum & Kontakt</h3>
            <p>Ouroboros Collective<br/>E-Mail: Rastamanweeste@gmail.com<br/>Weitere Bestimmungen in unserem offiziellen Endnutzer-Lizenzvertrag (EULA).</p>
          </section>
        </div>

        <div className="mt-6 pt-4 border-t border-stone-100">
          <button 
            onClick={onClose}
            className="w-full px-4 py-2 bg-stone-800 hover:bg-black text-white font-bold rounded-xl uppercase text-[10px] transition-all transform hover:-translate-y-0.5 hover:shadow-lg"
           >
            Akzeptieren & Schließen
          </button>
        </div>
      </div>
    </div>
  );
}
