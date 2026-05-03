import React from 'react';
import { 
  Check, 
  X, 
  Zap, 
  Crown, 
  ShieldCheck, 
  ArrowRight 
} from 'lucide-react';
import useBilling from '../../hooks/useBilling';

interface PaywallModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface PricingTier {
  id: string;
  name: string;
  price: string;
  description: string;
  features: string[];
  isPopular?: boolean;
  icon: React.ReactNode;
}

const PRICING_TIERS: PricingTier[] = [
  {
    id: 'free',
    name: 'Free',
    price: '€0',
    description: 'Für Einsteiger und kleine Projekte.',
    features: ['Bis zu 3 Projekte', 'Basis Support', 'Community Zugriff'],
    icon: <Zap className="w-5 h-5 text-gray-400" />
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '€19',
    description: 'Für Profis, die mehr Leistung benötigen.',
    features: ['Unlimitierte Projekte', 'Prioritäts-Support', 'Erweiterte Analysen', 'Team-Kollaboration'],
    isPopular: true,
    icon: <Crown className="w-5 h-5 text-yellow-500" />
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 'Custom',
    description: 'Maßgeschneiderte Lösungen für Teams.',
    features: ['Eigener Account Manager', 'SLA Garantien', 'SSO Integration', 'Custom Reporting'],
    icon: <ShieldCheck className="w-5 h-5 text-blue-500" />
  }
];

export const PaywallModal: React.FC<PaywallModalProps> = ({ 
  isOpen, 
  onClose 
}) => {
  const { purchase } = useBilling();

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-5xl bg-white dark:bg-slate-900 rounded-2xl shadow-2xl overflow-hidden border border-slate-200 dark:border-slate-800 animate-in fade-in zoom-in duration-300">
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        >
          <X className="w-5 h-5 text-slate-500" />
        </button>

        <div className="p-8 md:p-12">
          <div className="text-center mb-10">
            <h2 className="text-3xl font-bold text-slate-900 dark:text-white mb-4">
              Wähle den passenden Plan für dich
            </h2>
            <p className="text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
              Schalte alle Premium-Funktionen frei und skaliere dein Business mit unseren flexiblen Preismodellen.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {PRICING_TIERS.map((tier) => (
              <div 
                key={tier.id}
                className={`relative flex flex-col p-6 rounded-xl border ${
                  tier.isPopular 
                    ? 'border-blue-500 shadow-lg shadow-blue-500/10' 
                    : 'border-slate-200 dark:border-slate-800'
                } bg-white dark:bg-slate-900 transition-transform hover:scale-[1.02]`}
              >
                {tier.isPopular && (
                  <div className="absolute top-0 right-6 transform -translate-y-1/2">
                    <span className="bg-blue-500 text-white text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider">
                      Empfohlen
                    </span>
                  </div>
                )}

                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800">
                    {tier.icon}
                  </div>
                  <h3 className="text-xl font-bold text-slate-900 dark:text-white">{tier.name}</h3>
                </div>

                <div className="mb-6">
                  <span className="text-4xl font-extrabold text-slate-900 dark:text-white">{tier.price}</span>
                  {tier.id !== 'enterprise' && <span className="text-slate-500 ml-1">/ Monat</span>}
                </div>

                <p className="text-sm text-slate-600 dark:text-slate-400 mb-6 min-h-[40px]">
                  {tier.description}
                </p>

                <ul className="space-y-4 mb-8 flex-grow">
                  {tier.features.map((feature, idx) => (
                    <li key={idx} className="flex items-start gap-3 text-sm text-slate-700 dark:text-slate-300">
                      <Check className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
                      {feature}
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => purchase(tier.id)}
                  className={`w-full py-3 px-4 rounded-lg font-semibold flex items-center justify-center gap-2 transition-all ${
                    Boolean(tier.isPopular)
                      ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-md'
                      : 'bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-900 dark:text-white'
                  }`}
                >
                  <React.Fragment>
                    {tier.id === 'free' ? 'Aktueller Plan' : 'Plan wählen'}
                    <ArrowRight className="w-4 h-4" />
                  </React.Fragment>
                </button>
              </div>
            ))}
          </div>

          <div className="mt-10 text-center">
            <p className="text-xs text-slate-500 dark:text-slate-500">
              Sichere In-App Abwicklung. Keine versteckten Gebühren. Jederzeit kündbar.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PaywallModal;