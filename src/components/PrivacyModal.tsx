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
          <h2 className="text-lg font-black text-stone-800 tracking-tight">Datenschutz & Sicherheit</h2>
        </div>
        
        <div className="overflow-y-auto custom-scrollbar pr-2 space-y-4 text-xs text-stone-700 leading-relaxed flex-1">
          <section className="group hover:bg-stone-50 p-2 rounded-lg transition-colors">
            <h3 className="font-bold text-stone-900 text-sm mb-1 group-hover:text-indigo-700 transition-colors">1. Lokale Speicherung (Local Storage)</h3>
            <p>Unsere Anwendung speichert Ihre eingegebenen API-Schlüssel (GitHub PAT, Gemini API Key) sowie Nutzungsstatistiken <b>ausschließlich lokal</b> auf Ihrem Endgerät im Browser/App-Storage (<code>localStorage</code>).</p>
          </section>
          
          <section className="group hover:bg-stone-50 p-2 rounded-lg transition-colors">
            <h3 className="font-bold text-stone-900 text-sm mb-1 group-hover:text-indigo-700 transition-colors">2. Keine externe Datenübertragung an Dritte</h3>
            <p>Es werden keine Telemetriedaten, persönlichen Informationen oder API-Schlüssel an unsere eigenen Server gesendet. Die Kommunikation erfolgt direkt und verschlüsselt (TLS/SSL) über HTTPS zwischen Ihrem Client (der App) und den offiziellen Schnittstellen:</p>
            <ul className="list-disc pl-5 mt-1 space-y-1">
              <li><b>GitHub API</b> (api.github.com) für den Zugriff und das Pushen in Repositories.</li>
              <li><b>Google Gemini API</b> (generativelanguage.googleapis.com) für KI-Funktionalitäten.</li>
            </ul>
          </section>

          <section className="group hover:bg-stone-50 p-2 rounded-lg transition-colors">
            <h3 className="font-bold text-stone-900 text-sm mb-1 group-hover:text-indigo-700 transition-colors">3. Token-Sicherheit</h3>
            <p>Ihre API-Schlüssel sind für den Betrieb zwingend erforderlich und werden nicht extern persistiert. Wir empfehlen stets Token mit <b>minimalen Berechtigungen (Fine-grained PATs)</b> zu verwenden.</p>
          </section>
          
          <section className="group hover:bg-stone-50 p-2 rounded-lg transition-colors">
            <h3 className="font-bold text-stone-900 text-sm mb-1 group-hover:text-indigo-700 transition-colors">4. Verantwortlichkeit</h3>
            <p>Sie sind selbst für die Sicherheit Ihres Gerätes verantwortlich. Wenn Sie die App auf einem geteilten Gerät nutzen, empfehlen wir die Nutzung der "Cleanup"-Funktion oder das manuelle Löschen von Browserdaten nach Gebrauch, um Ihre Schlüssel zu entfernen.</p>
          </section>
        </div>

        <div className="mt-6 pt-4 border-t border-stone-100">
          <button 
            onClick={onClose}
            className="w-full px-4 py-2 bg-stone-800 hover:bg-black text-white font-bold rounded-xl uppercase text-[10px] transition-all transform hover:-translate-y-0.5 hover:shadow-lg"
           >
            Gelesen und Verstanden
          </button>
        </div>
      </div>
    </div>
  );
}
