import React, { useEffect, useCallback } from 'react';

interface PrivacyModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
}

const PrivacyModal: React.FC<PrivacyModalProps> = ({ 
  isOpen, 
  onClose, 
  title = 'Datenschutzerklärung (EU-DSGVO Konform)' 
}) => {
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      onClose();
    }
  }, [onClose]);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="privacy-modal-title"
    >
      <div 
        className="absolute inset-0 bg-slate-900/75 backdrop-blur-sm transition-opacity" 
        onClick={onClose}
      />
      
      <div className="relative bg-white dark:bg-slate-900 w-full max-w-3xl max-h-[90vh] overflow-hidden rounded-xl shadow-2xl flex flex-col border border-slate-200 dark:border-slate-800">
        <header className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between sticky top-0 bg-white dark:bg-slate-900 z-10">
          <h2 
            id="privacy-modal-title" 
            className="text-xl font-bold text-slate-900 dark:text-white"
          >
            {title}
          </h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 transition-colors"
            aria-label="Modal schließen"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 text-slate-600 dark:text-slate-300 leading-relaxed space-y-6">
          <section>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">1. Datenschutz auf einen Blick</h3>
            <p>
              Die Betreiber dieser Seiten nehmen den Schutz Ihrer persönlichen Daten sehr ernst. Wir behandeln Ihre personenbezogenen Daten vertraulich und entsprechend der gesetzlichen Datenschutzvorschriften sowie dieser Datenschutzerklärung.
            </p>
          </section>

          <section>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">2. Datenerfassung auf unserer Website</h3>
            <p>
              Die Datenverarbeitung auf dieser Website erfolgt durch den Websitebetreiber. Dessen Kontaktdaten können Sie dem Impressum dieser Website entnehmen. Ihre Daten werden zum einen dadurch erhoben, dass Sie uns diese mitteilen. Dies können z.B. Daten sein, die Sie in ein Kontaktformular eingeben.
            </p>
            <p className="mt-2">
              Andere Daten werden automatisch beim Besuch der Website durch unsere IT-Systeme erfasst. Das sind vor allem technische Daten (z.B. Internetbrowser, Betriebssystem oder Uhrzeit des Seitenaufrufs).
            </p>
          </section>

          <section>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">3. Ihre Rechte nach DSGVO</h3>
            <p>Sie haben im Rahmen der geltenden gesetzlichen Bestimmungen jederzeit das Recht auf:</p>
            <ul className="list-disc ml-6 mt-2 space-y-1">
              <li>Auskunft über Ihre gespeicherten personenbezogenen Daten</li>
              <li>Berichtigung oder Löschung Ihrer Daten</li>
              <li>Einschränkung der Verarbeitung</li>
              <li>Datenübertragbarkeit</li>
              <li>Widerruf erteilter Einwilligungen</li>
            </ul>
          </section>

          <section>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">4. Hosting und Content Delivery Networks (CDN)</h3>
            <p>
              Wir hosten die Inhalte unserer Website bei folgendem Anbieter: Cloud-Infrastruktur innerhalb der Europäischen Union. Die Verarbeitung erfolgt auf Grundlage von Art. 6 Abs. 1 lit. f DSGVO. Unser berechtigtes Interesse besteht an einer möglichst zuverlässigen Darstellung unserer Website.
            </p>
          </section>

          <section>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">5. TLS-Verschlüsselung</h3>
            <p>
              Diese Seite nutzt aus Sicherheitsgründen und zum Schutz der Übertragung vertraulicher Inhalte eine TLS-Verschlüsselung. Eine verschlüsselte Verbindung erkennen Sie daran, dass die Adresszeile des Browsers von „http://“ auf „https://“ wechselt.
            </p>
          </section>
        </div>

        <footer className="px-6 py-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-800 rounded-lg transition-colors"
          >
            Abbrechen
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors"
          >
            Verstanden & Schließen
          </button>
        </footer>
      </div>
    </div>
  );
};

export default PrivacyModal;