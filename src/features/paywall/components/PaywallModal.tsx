import React, { useState, useEffect } from 'react';
import { Check, X, Crown, Zap, Shield, Star } from 'lucide-react';

interface Plan {
  id: string;
  name: string;
  price: string;
  period: string;
  description: string;
  features: string[];
  isPopular?: boolean;
  buttonText: string;
}

interface PaywallModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubscribe: (planId: string) => void;
}

const PLANS: Plan[] = [
  {
    id: 'basic',
    name: 'Basic',
    price: '0€',
    period: '/Monat',
    description: 'Perfekt für den Einstieg und zum Ausprobieren.',
    features: ['Eingeschränkter Zugriff', 'Community Support', 'Standard Geschwindigkeit'],
    buttonText: 'Kostenlos starten'
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '19€',
    period: '/Monat',
    description: 'Für Power-User, die maximale Leistung benötigen.',
    features: ['Unbegrenzter Zugriff', 'Priorisierter Support', 'Maximale Geschwindigkeit', 'Exklusive Features'],
    isPopular: true,
    buttonText: 'Jetzt upgraden'
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: '49€',
    period: '/Monat',
    description: 'Maßgeschneiderte Lösungen für große Teams.',
    features: ['Alles aus Pro', 'Dedizierter Account Manager', 'SLA Garantien', 'Custom Integrationen'],
    buttonText: 'Kontakt aufnehmen'
  }
];

export const PaywallModal: React.FC<PaywallModalProps> = ({ isOpen, onClose, onSubscribe }) => {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setIsVisible(true);
      document.body.style.overflow = 'hidden';
    } else {
      const timer = setTimeout(() => setIsVisible(false), 300);
      document.body.style.overflow = 'unset';
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  if (!isOpen && !isVisible) return null;

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0'}`}>
      <div 
        className="absolute inset-0 bg-black/60 backdrop-blur-sm" 
        onClick={onClose}
      />
      
      <div className={`relative w-full max-w-5xl bg-white rounded-3xl shadow-2xl overflow-hidden transition-transform duration-300 ${isOpen ? 'scale-100' : 'scale-95'}`}>
        <button 
          onClick={onClose}
          className="absolute top-6 right-6 p-2 rounded-full hover:bg-gray-100 transition-colors z-10"
        >
          <X className="w-6 h-6 text-gray-500" />
        </button>

        <div className="flex flex-col lg:flex-row">
          <div className="lg:w-1/3 bg-gray-50 p-8 lg:p-12">
            <div className="mb-8">
              <div className="w-12 h-12 bg-indigo-600 rounded-2xl flex items-center justify-center mb-6">
                <Crown className="text-white w-7 h-7" />
              </div>
              <h2 className="text-3xl font-bold text-gray-900 leading-tight">
                Schalte das volle Potenzial frei
              </h2>
              <p className="mt-4 text-gray-600">
                Wähle den passenden Plan für deine Bedürfnisse und starte noch heute durch.
              </p>
            </div>

            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="mt-1 bg-green-100 rounded-full p-1">
                  <Shield className="w-4 h-4 text-green-600" />
                </div>
                <p className="text-sm text-gray-600">Sichere Zahlungsabwicklung</p>
              </div>
              <div className="flex items-start gap-3">
                <div className="mt-1 bg-blue-100 rounded-full p-1">
                  <Zap className="w-4 h-4 text-blue-600" />
                </div>
                <p className="text-sm text-gray-600">Sofortiger Zugriff auf alle Features</p>
              </div>
              <div className="flex items-start gap-3">
                <div className="mt-1 bg-yellow-100 rounded-full p-1">
                  <Star className="w-4 h-4 text-yellow-600" />
                </div>
                <p className="text-sm text-gray-600">Jederzeit kündbar</p>
              </div>
            </div>
          </div>

          <div className="lg:w-2/3 p-8 lg:p-12">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {PLANS.map((plan) => (
                <div 
                  key={plan.id}
                  className={`relative flex flex-col p-6 rounded-2xl border-2 transition-all duration-200 ${
                    plan.isPopular 
                      ? 'border-indigo-600 shadow-lg scale-105 z-10 bg-white' 
                      : 'border-gray-100 hover:border-gray-200 bg-gray-50/50'
                  }`}
                >
                  {plan.isPopular && (
                    <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider">
                      Empfohlen
                    </div>
                  )}

                  <div className="mb-4">
                    <h3 className="text-lg font-bold text-gray-900">{plan.name}</h3>
                    <div className="mt-2 flex items-baseline">
                      <span className="text-3xl font-extrabold text-gray-900">{plan.price}</span>
                      <span className="text-sm text-gray-500 ml-1">{plan.period}</span>
                    </div>
                  </div>

                  <p className="text-sm text-gray-600 mb-6 flex-grow">
                    {plan.description}
                  </p>

                  <ul className="space-y-3 mb-8">
                    {plan.features.map((feature, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <Check className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                        <span className="text-xs text-gray-700">{feature}</span>
                      </li>
                    ))}
                  </ul>

                  <button
                    onClick={() => onSubscribe(plan.id)}
                    className={`w-full py-3 px-4 rounded-xl font-semibold text-sm transition-all duration-200 ${
                      plan.isPopular
                        ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-md shadow-indigo-200'
                        : 'bg-white text-gray-900 border border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    {plan.buttonText}
                  </button>
                </div>
              ))}
            </div>
            
            <p className="mt-8 text-center text-xs text-gray-400">
              Preise inkl. MwSt. Alle Pläne unterliegen unseren Nutzungsbedingungen. 
              Du kannst dein Abonnement jederzeit in den Einstellungen verwalten.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PaywallModal;