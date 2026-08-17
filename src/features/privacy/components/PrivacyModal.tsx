import React, { useEffect, useRef } from 'react';

interface PrivacyModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const PrivacyModal: React.FC<PrivacyModalProps> = ({ isOpen, onClose }) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const firstFocusableRef = useRef<HTMLButtonElement>(null);
  const lastFocusableRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      firstFocusableRef.current?.focus();

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          onClose();
        }

        if (e.key === 'Tab') {
          if (e.shiftKey) {
            if (document.activeElement === firstFocusableRef.current) {
              e.preventDefault();
              lastFocusableRef.current?.focus();
            }
          } else {
            if (document.activeElement === lastFocusableRef.current) {
              e.preventDefault();
              firstFocusableRef.current?.focus();
            }
          }
        }
      };

      document.addEventListener('keydown', handleKeyDown);
      return () => {
        document.removeEventListener('keydown', handleKeyDown);
        document.body.style.overflow = '';
      };
    }
    return undefined;
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black bg-opacity-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="privacy-modal-title"
    >
      <div
        ref={modalRef}
        className="relative w-full max-w-2xl p-6 mx-4 bg-white rounded-lg shadow-xl dark:bg-gray-800"
      >
        <div className="flex items-center justify-between mb-4 border-b pb-2">
          <h2
            id="privacy-modal-title"
            className="text-xl font-semibold text-gray-900 dark:text-white"
          >
            Datenschutzbestimmungen
          </h2>
          <button
            ref={firstFocusableRef}
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            aria-label="Schließen"
          >
            <span className="text-2xl" aria-hidden="true">&times;</span>
          </button>
        </div>
        
        <div className="space-y-4 overflow-y-auto max-h-96 text-gray-600 dark:text-gray-300">
          <section>
            <h3 className="font-bold text-gray-900 dark:text-white">1. Identität der App und des Anbieters</h3>
            <p>
              Diese Datenschutzerklärung gilt für <strong>ARE-LOGIK - NOCode Studio</strong>
              {' '}mit der Android-Paket-ID <code>com.arestudio.nocode.aab</code>.
            </p>
            <p>
              Google-Play-Entwicklername: <strong>ARE-LOGIC ENGINE</strong>. Verantwortliche Person/Anbieterin:
              {' '}<strong>Susanne Möller</strong>, Schwarzenmoorstr. 117, 32049 Herford, Deutschland.
            </p>
          </section>
          <section>
            <h3 className="font-bold text-gray-900 dark:text-white">2. Welche Daten verarbeitet werden</h3>
            <p>
              Je nach verwendeter Funktion verarbeitet die App Konto- und Anmeldedaten (z. B. E-Mail-Adresse,
              Anzeigename und Authentifizierungskennungen), von Ihnen bereitgestellte Projekt-, Datei-, Repository-
              oder Chat-Inhalte sowie technische Verbindungs- und Geräteinformationen, die für sicheren Betrieb,
              Fehlerdiagnose und Missbrauchsschutz erforderlich sind.
            </p>
            <p>
              Wenn optionale Telemetrie aktiviert ist, können pseudonymisierte Nutzungsereignisse verarbeitet werden.
              Zahlungsanbieter verarbeiten Zahlungsdaten in ihren eigenen Systemen; die App benötigt für Freischaltungen
              nur Zahlungs-/Entitlement-Status und speichert keine vollständigen Karten- oder Bankzugangsdaten.
            </p>
          </section>
          <section>
            <h3 className="font-bold text-gray-900 dark:text-white">3. Zweck, Weitergabe und Speicherdauer</h3>
            <p>
              Daten werden zur Bereitstellung der App, Authentifizierung, Ausführung ausdrücklich angeforderter Funktionen,
              Abrechnung/Freischaltung, Sicherheit, Support und Fehleranalyse verarbeitet. Eine Weitergabe erfolgt nur,
              soweit sie für die jeweils genutzte Funktion erforderlich ist, etwa an einen von Ihnen gewählten Login-,
              Hosting-, Repository-, Modell- oder Zahlungsdienst. Es findet kein Verkauf personenbezogener Daten statt.
            </p>
            <p>
              Daten werden nur solange aufbewahrt, wie dies für den jeweiligen Zweck, gesetzliche Pflichten oder die
              Sicherheit des Dienstes erforderlich ist. Nutzer können die Löschung ihrer Kontodaten verlangen.
            </p>
          </section>
          <section>
            <h3 className="font-bold text-gray-900 dark:text-white">4. Ihre Rechte und Kontakt</h3>
            <p>
              Sie haben im gesetzlichen Rahmen Rechte auf Auskunft, Berichtigung, Löschung, Einschränkung,
              Datenübertragbarkeit und Widerspruch. Datenschutzanfragen können an
              {' '}<a className="underline" href="mailto:projectouroboroscollective@gmail.com">projectouroboroscollective@gmail.com</a>
              {' '}gerichtet werden.
            </p>
            <p>
              Die öffentlich abrufbare Fassung dieser Erklärung ist unter
              {' '}<a className="underline" href="/privacy.html" target="_blank" rel="noreferrer">/privacy.html</a> verfügbar.
            </p>
          </section>
        </div>

        <div className="mt-6 flex justify-end">
          <button
            ref={lastFocusableRef}
            onClick={onClose}
            className="px-4 py-2 text-white bg-blue-600 rounded hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            Verstanden
          </button>
        </div>
      </div>
    </div>
  );
};

export default PrivacyModal;