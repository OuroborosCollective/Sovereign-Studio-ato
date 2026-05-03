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
            <h3 className="font-bold text-gray-900 dark:text-white">1. Datenerfassung</h3>
            <p>Wir erfassen nur technisch notwendige Daten, um die Funktionalität dieser Anwendung zu gewährleisten.</p>
          </section>
          <section>
            <h3 className="font-bold text-gray-900 dark:text-white">2. Datennutzung</h3>
            <p>Ihre Daten werden nicht an Dritte weitergegeben und ausschließlich lokal oder in gesicherten Umgebungen verarbeitet.</p>
          </section>
          <section>
            <h3 className="font-bold text-gray-900 dark:text-white">3. Ihre Rechte</h3>
            <p>Sie haben jederzeit das Recht auf Auskunft, Berichtigung oder Löschung Ihrer gespeicherten Daten.</p>
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