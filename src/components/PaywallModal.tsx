import React, { useState, useEffect } from 'react';
import { Unlock, Info, Shield, AlertTriangle } from 'lucide-react';

interface PaywallModalProps {
  show: boolean;
  onClose: () => void;
  onUpgrade: () => void;
}

export function PaywallModal({ show, onClose, onUpgrade }: PaywallModalProps) {
  const [clickTime, setClickTime] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Reset error when modal closes
  useEffect(() => {
    if (!show) {
      setErrorMsg(null);
    }
  }, [show]);

  const handleLinkClick = () => {
    setClickTime(Date.now());
    setErrorMsg(null);
  };

  const handleVerify = () => {
    if (!clickTime) {
      setErrorMsg("Bitte klicke zuerst auf den PayPal-Link, um die Zahlung zu starten.");
      return;
    }
    
    const timePassedMs = Date.now() - clickTime;
    const requiredWaitMs = 60000; // 1 minute
    
    if (timePassedMs < requiredWaitMs) {
      const remainingSeconds = Math.ceil((requiredWaitMs - timePassedMs) / 1000);
      setErrorMsg(`Verifizierung läuft noch... Bitte schließe die Zahlung zuerst vollständig bei PayPal ab. Versuche es in ${remainingSeconds} Sekunden erneut.`);
      return;
    }

    onUpgrade();
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-stone-900/60 z-[100] flex items-center justify-center p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 text-center border border-stone-200 animate-in zoom-in-95 duration-200">
        <div className="w-16 h-16 bg-gradient-to-br from-indigo-500 to-purple-600 text-white rounded-full flex items-center justify-center mx-auto mb-4 shadow-md transform hover:scale-110 transition-transform">
          <Unlock size={28} />
        </div>
        <h2 className="text-xl font-black text-stone-800 mb-2 tracking-tight">Lebenslange Freischaltung</h2>
        <p className="text-stone-600 text-sm mb-6 leading-relaxed">
          Du hast das kostenlose Limit für diesen Account erreicht. 
          Schalte die unbegrenzte Nutzung des PR Auto-Resolvers und der Ideen-Generation jetzt dauerhaft frei.
        </p>
        
        <div className="bg-stone-50 border border-stone-200 rounded-xl p-4 mb-4 text-left hover:border-indigo-200 transition-colors">
          <ol className="list-decimal pl-4 text-xs text-stone-700 space-y-3 font-medium">
            <li>Nutze diesen Link für eine einmalige <b>Zahlung über 5,55 €</b>: <br/>
              <div className="mt-1.5 bg-white border border-stone-300 px-3 py-2 rounded-lg font-mono text-indigo-700 font-bold break-all flex items-center gap-2 hover:bg-stone-50 transition-colors">
                <a 
                  href="https://www.paypal.com/ncp/payment/PDQS23735S9KJ" 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  onClick={handleLinkClick}
                  className="hover:underline flex items-center gap-1 group"
                >
                  Zahle mit PayPal <Info size={12} className="group-hover:text-indigo-500 transition-colors" />
                </a>
              </div>
            </li>
            <li>Darin enthalten: kompletter Editor-Zugriff sowie der <b>Full-Workflow</b>: Kreation, Linting, Fixing, Datenbankanbindung und Deployment in einem Rutsch.</li>
            <li>Ebenfalls freigeschaltet: Einbindung von Datenblättern und komplexen PDFs als Kontext für das Projekt.</li>
            <li className="text-stone-500 italic">Für diesen Release: Nutze PayPal und bestätige unten die erfolgreiche Transaktion zur sofortigen Freischaltung.</li>
          </ol>
        </div>

        {errorMsg && (
          <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-3 py-2.5 rounded-lg text-xs font-bold flex items-start gap-2 text-left animate-in slide-in-from-top-2">
            <AlertTriangle size={14} className="shrink-0 mt-0.5" />
            <p>{errorMsg}</p>
          </div>
        )}

        <div className="flex gap-2">
          <button 
            onClick={onClose}
            className="flex-1 px-4 py-2.5 bg-stone-100 hover:bg-stone-200 text-stone-600 font-bold rounded-xl uppercase text-[10px] transition-all hover:shadow-inner"
          >
            Vielleicht Später
          </button>
          <button 
            onClick={handleVerify}
            className="flex-1 px-4 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-bold rounded-xl uppercase text-[10px] transition-all shadow-md transform hover:scale-[1.02]"
          >
            Zahlung bestätigt
          </button>
        </div>
      </div>
    </div>
  );
}
