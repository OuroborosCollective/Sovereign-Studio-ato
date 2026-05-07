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
            Datenschutzerklärung & Privatsphäre
          </h2>
          <button 
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
            aria-label="Schließen"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 text-slate-600 dark:text-slate-300 space-y-4 text-sm leading-relaxed">
          <section>
            <h3 className="font-semibold text-slate-900 dark:text-white mb-2">1. Allgemeine Informationen</h3>
            <p>
              Wir freuen uns über Ihr Interesse an unserer Anwendung. Der Schutz Ihrer Privatsphäre ist für uns von höchster Bedeutung. Im Folgenden informieren wir Sie detailliert über den Umgang mit Ihren Daten.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-slate-900 dark:text-white mb-2">2. Datenerfassung</h3>
            <p>
              Beim Zugriff auf diese Anwendung werden automatisch Informationen allgemeiner Natur erfasst. Diese Informationen (Server-Logfiles) beinhalten etwa die Art des Webbrowsers, das verwendete Betriebssystem und den Domainnamen Ihres Internet-Service-Providers.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-slate-900 dark:text-white mb-2">3. Cookies & Local Storage</h3>
            <p>
              Wir verwenden technisch notwendige Cookies und Local Storage Einträge, um die Funktionalität der Anwendung zu gewährleisten und Ihre Präferenzen (wie z.B. Dark Mode Einstellungen) zu speichern.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-slate-900 dark:text-white mb-2">4. Ihre Rechte</h3>
            <p>
              Sie haben jederzeit das Recht auf unentgeltliche Auskunft über Ihre gespeicherten personenbezogenen Daten, deren Herkunft und Empfänger und den Zweck der Datenverarbeitung sowie ein Recht auf Berichtigung, Sperrung oder Löschung dieser Daten.
            </p>
          </section>

          <section className="bg-slate-50 dark:bg-slate-800/50 p-4 rounded-lg border border-slate-100 dark:border-slate-800">
            <p className="text-xs italic">
              Durch Klicken auf "Akzeptieren" stimmen Sie der Speicherung von Cookies auf Ihrem Gerät zu, um die Navigation zu verbessern und die Nutzung der Anwendung zu analysieren.
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