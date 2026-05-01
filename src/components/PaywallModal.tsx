import React from 'react';
import { Unlock, Info, Shield } from 'lucide-react';

interface PaywallModalProps {
  show: boolean;
  onClose: () => void;
  onUpgrade: () => void;
}

export function PaywallModal({ show, onClose, onUpgrade }: PaywallModalProps) {
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
        
        <div className="bg-stone-50 border border-stone-200 rounded-xl p-4 mb-6 text-left hover:border-indigo-200 transition-colors">
          <ol className="list-decimal pl-4 text-xs text-stone-700 space-y-3 font-medium">
            <li>Nutze diesen Link für eine einmalige <b>PayPal Zahlung über 5,55 €</b>: <br/>
              <div className="mt-1.5 bg-white border border-stone-300 px-3 py-2 rounded-lg font-mono text-indigo-700 font-bold break-all flex items-center gap-2 hover:bg-stone-50 transition-colors">
                <a href="https://www.paypal.com/ncp/payment/PDQS23735S9KJ" target="_blank" rel="noopener noreferrer" className="hover:underline flex items-center gap-1 group">
                  Zahle mit PayPal <Info size={12} className="group-hover:text-indigo-500 transition-colors" />
                </a>
              </div>
            </li>
            <li>Nach Freigabe der App kann der Kauf auch regulär über In-App-Purchase im Play Store durchgeführt werden.</li>
            <li className="text-stone-500 italic">Für diesen Release: Nutze PayPal und bestätige unten die erfolgreiche Transaktion zur sofortigen Freischaltung.</li>
          </ol>
        </div>

        <div className="flex gap-2">
          <button 
            onClick={onClose}
            className="flex-1 px-4 py-2.5 bg-stone-100 hover:bg-stone-200 text-stone-600 font-bold rounded-xl uppercase text-[10px] transition-all hover:shadow-inner"
          >
            Vielleicht Später
          </button>
          <button 
            onClick={onUpgrade}
            className="flex-1 px-4 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-bold rounded-xl uppercase text-[10px] transition-all shadow-md transform hover:scale-[1.02]"
          >
            Zahlung bestätigt
          </button>
        </div>
      </div>
    </div>
  );
}
