import React, { useEffect } from 'react';

interface PrivacyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAccept: () => void;
  onDecline?: () => void;
}

export const PrivacyModal: React.FC<PrivacyModalProps> = ({
  isOpen,
  onClose,
  onAccept,
  onDecline
}) => {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="bg-white dark:bg-slate-900 w-full max-w-2xl rounded-xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden border border-slate-200 dark:border-slate-800 animate-in zoom-in-95 duration-200"
        role="dialog"
        aria-modal="true"
        aria-labelledby="privacy-title"
      >
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center">
          <h2 id="privacy-title" className="text-xl font-bold text-slate-900 dark:text-white">
            Datenschutzerklärung & EU-DSGVO
          </h2>
          <button 
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
            aria-label="Schließen"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 text-slate-600 dark:text-slate-300 space-y-5 text-sm leading-relaxed">
          <section>
            <h3 className="font-semibold text-slate-900 dark:text-white mb-2">1. Verantwortliche Stelle</h3>
            <p>
              Verantwortlich für die Datenverarbeitung in dieser Anwendung ist der Betreiber. Bei Fragen zum Datenschutz können Sie sich jederzeit an den Support wenden.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-slate-900 dark:text-white mb-2">2. KI-Datenverarbeitung (Google Gemini API)</h3>
            <p>
              Diese Anwendung nutzt die Google Gemini API zur Verarbeitung von Texteingaben. Gemäß Google Play Data Safety Richtlinien weisen wir darauf hin:
            </p>
            <ul className="list-disc ml-5 mt-2 space-y-1">
              <li>Ihre Eingaben (Prompts) werden verschlüsselt an Server der Google Ireland Limited übertragen.</li>
              <li>Die Daten werden ausschließlich zur Generierung der Antwort verarbeitet.</li>
              <li>Es findet keine dauerhafte Verknüpfung Ihrer persönlichen Identität mit den KI-Anfragen statt, sofern nicht technisch für den Dienst erforderlich.</li>
            </ul>
          </section>

          <section>
            <h3 className="font-semibold text-slate-900 dark:text-white mb-2">3. Ihre Rechte nach EU-DSGVO</h3>
            <p>Sie haben gegenüber uns folgende Rechte hinsichtlich der Sie betreffenden personenbezogenen Daten:</p>
            <ul className="list-disc ml-5 mt-2 space-y-1">
              <li><strong>Recht auf Auskunft (Art. 15 DSGVO):</strong> Sie können Informationen über Ihre von uns verarbeiteten Daten verlangen.</li>
              <li><strong>Recht auf Berichtigung (Art. 16 DSGVO):</strong> Korrektur unrichtiger Daten.</li>
              <li><strong>Recht auf Löschung (Art. 17 DSGVO):</strong> Sie können die unverzügliche Löschung Ihrer Daten fordern ("Recht auf Vergessenwerden").</li>
              <li><strong>Recht auf Datenübertragbarkeit (Art. 20 DSGVO):</strong> Erhalt Ihrer Daten in einem strukturierten, gängigen Format.</li>
              <li><strong>Widerrufsrecht:</strong> Erteilte Einwilligungen können Sie jederzeit mit Wirkung für die Zukunft widerrufen.</li>
            </ul>
          </section>

          <section>
            <h3 className="font-semibold text-slate-900 dark:text-white mb-2">4. Datensicherheit</h3>
            <p>
              Wir setzen technische und organisatorische Sicherheitsmaßnahmen ein, um Ihre Daten gegen Manipulationen, Verlust oder unbefugten Zugriff zu schützen. Alle Datenübertragungen erfolgen über eine gesicherte TLS-Verschlüsselung (HTTPS).
            </p>
          </section>

          <section className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg border border-blue-100 dark:border-blue-800/50">
            <p className="text-xs text-blue-800 dark:text-blue-300">
              Mit dem Klick auf "Alle akzeptieren" willigen Sie in die oben beschriebene Verarbeitung Ihrer Daten, insbesondere in den Datenaustausch mit der Google Gemini API zur Bereitstellung der KI-Funktionen, ein.
            </p>
          </section>
        </div>

        <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex flex-col sm:flex-row justify-end gap-3">
          <button
            onClick={onDecline || onClose}
            className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-800 rounded-lg transition-colors border border-slate-300 dark:border-slate-700"
          >
            Ablehnen
          </button>
          <button
            onClick={onAccept}
            className="px-6 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm shadow-blue-500/20 transition-all active:scale-95"
          >
            Alle akzeptieren
          </button>
        </div>
      </div>
    </div>
  );
};

export default PrivacyModal;