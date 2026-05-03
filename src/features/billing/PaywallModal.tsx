import React, { useState } from 'react';
import { 
  Check, 
  X, 
  Zap, 
  Crown, 
  ShieldCheck, 
  ArrowRight,
  Loader2
} from 'lucide-react';
import { useBilling } from './hooks/useBilling';

type TierId = 'free' | 'pro' | 'enterprise';

interface PricingTier {
  id: TierId;
  name: string;
  price: string;
  description: string;
  features: string[];
  credits: number | 'Unlimited';
  isPopular?: boolean;
  icon: React.ReactNode;
}

const PRICING_TIERS: PricingTier[] = [
  {
    id: 'free',
    name: 'Free',
    price: '€0',
    credits: 10,
    description: 'Für Einsteiger und kleine Projekte.',
    features: ['10 Design Credits', 'Basis Support', 'Community Zugriff'],
    icon: <Zap className="w-5 h-5 text-gray-400" />
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '€19',
    credits: 500,
    description: 'Für Profis, die mehr Leistung benötigen.',
    features: ['500 Design Credits', 'Prioritäts-Support', 'Erweiterte Analysen', 'Team-Kollaboration'],
    isPopular: true,
    icon: <Crown className="w-5 h-5 text-yellow-500" />
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 'Custom',
    credits: 'Unlimited',
    description: 'Maßgeschneiderte Lösungen für Teams.',
    features: ['Unlimitierte Credits', 'Eigener Account Manager', 'SLA Garantien', 'Custom Reporting'],
    icon: <ShieldCheck className="w-5 h-5 text-blue-500" />
  }
];

interface PaywallModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const PaywallModal: React.FC<PaywallModalProps> = ({ 
  isOpen, 
  onClose 
}) => {
  const { purchase, isProcessing } = useBilling();
  const [loadingTier, setLoadingTier] = useState<TierId | null>(null);

  if (!isOpen) return null;

  const handlePurchase = async (tierId: TierId) => {
    if (tierId === 'free') return;
    
    setLoadingTier(tierId);
    try {
      await purchase(tierId);
      onClose();
    } catch (error) {
      console.error('Purchase transaction failed:', error);
    } finally {
      setLoadingTier(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
      <div className="relative w-full max-w-6xl bg-white dark:bg-slate-900 rounded-3xl shadow-2xl overflow-hidden border border-slate-200 dark:border-slate-800 animate-in fade-in zoom-in duration-300">
        <button 
          type="button"
          onClick={onClose}
          className="absolute top-6 right-6 p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors z-10"
        >
          <X className="w-6 h-6 text-slate-500" />
        </button>

        <div className="p-8 md:p-14">
          <div className="text-center mb-12">
            <h2 className="text-4xl font-black text-slate-900 dark:text-white mb-4 tracking-tight">
              Upgrade dein Creative-Potenzial
            </h2>
            <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
              Wähle den Plan, der zu deinem Workflow passt, und schalte sofort Credits für die Canvas-Generierung frei.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {PRICING_TIERS.map((tier) => {
              const isLoading = loadingTier === tier.id || (isProcessing && loadingTier === tier.id);
              
              return (
                <div 
                  key={tier.id}
                  className={`relative flex flex-col p-8 rounded-2xl border-2 transition-all duration-300 ${
                    tier.isPopular 
                      ? 'border-blue-500 shadow-xl shadow-blue-500/10 bg-blue-50/30 dark:bg-blue-900/10 scale-105 z-10' 
                      : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700'
                  }`}
                >
                  {tier.isPopular && (
                    <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
                      <span className="bg-blue-600 text-white text-xs font-black px-4 py-1.5 rounded-full uppercase tracking-widest shadow-lg">
                        Meistgewählt
                      </span>
                    </div>
                  )}

                  <div className="flex items-center gap-4 mb-6">
                    <div className={`p-3 rounded-xl ${tier.isPopular ? 'bg-blue-100 dark:bg-blue-900/30' : 'bg-slate-100 dark:bg-slate-800'}`}>
                      {tier.icon}
                    </div>
                    <div>
                      <h3 className="text-xl font-bold text-slate-900 dark:text-white">{tier.name}</h3>
                      <p className="text-xs font-medium text-blue-600 dark:text-blue-400 uppercase tracking-wider">
                        {tier.credits} Credits inklusive
                      </p>
                    </div>
                  </div>

                  <div className="mb-6">
                    <div className="flex items-baseline gap-1">
                      <span className="text-5xl font-black text-slate-900 dark:text-white">{tier.price}</span>
                      {tier.id !== 'enterprise' && (
                        <span className="text-slate-500 font-medium">/ Monat</span>
                      )}
                    </div>
                  </div>

                  <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400 mb-8 min-h-[48px]">
                    {tier.description}
                  </p>

                  <div className="space-y-4 mb-10 flex-grow">
                    {tier.features.map((feature, idx) => (
                      <div key={idx} className="flex items-start gap-3">
                        <div className="mt-1 bg-green-500/10 rounded-full p-0.5">
                          <Check className="w-3.5 h-3.5 text-green-500" />
                        </div>
                        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{feature}</span>
                      </div>
                    ))}
                  </div>

                  <button
                    type="button"
                    onClick={() => handlePurchase(tier.id)}
                    disabled={tier.id === 'free' || isProcessing}
                    className={`group relative w-full py-4 px-6 rounded-xl font-bold flex items-center justify-center gap-3 transition-all active:scale-[0.98] ${
                      tier.isPopular 
                        ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-500/25'
                        : 'bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-900 dark:text-white'
                    } ${tier.id === 'free' ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    {isLoading ? (
                      <Loader2 className="w-5 h-5 animate-spin text-white" />
                    ) : (
                      <React.Fragment>
                        <span>{tier.id === 'free' ? 'Aktueller Plan' : 'Jetzt upgraden'}</span>
                        <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                      </React.Fragment>
                    )}
                  </button>
                </div>
              );
            })}
          </div>

          <div className="mt-14 pt-8 border-t border-slate-100 dark:border-slate-800 flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-8">
              <div className="flex flex-col">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Sicherheit</span>
                <span className="text-sm font-medium text-slate-600 dark:text-slate-400 italic">SSL-verschlüsselt</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Flexibilität</span>
                <span className="text-sm font-medium text-slate-600 dark:text-slate-400">Jederzeit kündbar</span>
              </div>
            </div>
            <p className="text-xs text-slate-400 dark:text-slate-500 text-center md:text-right max-w-sm">
              Mit dem Kauf akzeptieren Sie unsere Nutzungsbedingungen. Die Credits werden sofort nach Zahlungseingang deinem Account gutgeschrieben.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PaywallModal;