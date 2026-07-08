import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { 
  Check, 
  X, 
  Zap, 
  Crown, 
  ShieldCheck, 
  ArrowRight,
  Loader2,
  Sparkles
} from 'lucide-react';
import { useBilling } from './hooks/useBilling';
import type { BillingPackage } from './billingSlice';

interface PaywallModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// Icon map for payment methods (from backend config)
const TierIcon: React.FC<{ tier: string }> = ({ tier }) => {
  switch (tier) {
    case 'pro':
    case 'premium':
      return <Crown className="w-5 h-5 text-yellow-500" />;
    case 'enterprise':
      return <ShieldCheck className="w-5 h-5 text-blue-500" />;
    default:
      return <Zap className="w-5 h-5 text-slate-400" />;
  }
};

export const PaywallModal: React.FC<PaywallModalProps> = ({ 
  isOpen, 
  onClose 
}) => {
  const { purchase, isProcessing, currentPlanId, packages } = useBilling();
  const [loadingTier, setLoadingTier] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen || !mounted) return null;

  // Use backend packages if available, otherwise show loading
  const displayPackages: BillingPackage[] = packages.length > 0 
    ? packages 
    : [];

  const handlePurchase = async (packageId: string) => {
    if (packageId === currentPlanId) return;
    
    setLoadingTier(packageId);
    try {
      await purchase(packageId);
      onClose();
    } catch (error) {
      console.error('Billing Error:', error);
    } finally {
      setLoadingTier(null);
    }
  };

  const modalContent = (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
      <div 
        className="absolute inset-0 bg-slate-950/40 backdrop-blur-xl transition-opacity animate-in fade-in duration-300"
        onClick={onClose}
      />
      
      <div className="relative w-full max-w-6xl bg-white dark:bg-slate-950 rounded-[2.5rem] shadow-[0_0_50px_-12px_rgba(0,0,0,0.5)] overflow-hidden border border-slate-200 dark:border-white/10 animate-in zoom-in-95 duration-300">
        <button 
          type="button"
          onClick={onClose}
          className="absolute top-8 right-8 p-2.5 rounded-full bg-slate-100 dark:bg-white/5 hover:bg-slate-200 dark:hover:bg-white/10 transition-all z-20"
        >
          <X className="w-5 h-5 text-slate-500 dark:text-slate-400" />
        </button>

        <div className="grid grid-cols-1 lg:grid-cols-12 min-h-[600px]">
          <div className="lg:col-span-12 p-8 md:p-16">
            <div className="flex flex-col items-center text-center mb-12">
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 text-xs font-bold uppercase tracking-widest mb-6">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Premium Access</span>
              </div>
              <h2 className="text-4xl md:text-5xl font-black text-slate-900 dark:text-white mb-4 tracking-tight leading-tight">
                Bereit für das nächste Level?
              </h2>
              <p className="text-lg text-slate-500 dark:text-slate-400 max-w-2xl">
                Wähle deinen Plan und schalte sofortige Design-Power frei. 
                Keine versteckten Gebühren, volle Transparenz.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
              {displayPackages.length === 0 ? (
                // Fallback when no packages loaded
                <div className="col-span-3 flex items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                  <span className="ml-3 text-slate-400">Lade Pakete...</span>
                </div>
              ) : (
                displayPackages.map((pkg) => {
                  const isCurrent = currentPlanId === pkg.id;
                  const isLoading = loadingTier === pkg.id;
                  const isPopular = pkg.isPopular || pkg.isRecommended;
                  
                  return (
                    <div 
                      key={pkg.id}
                      className={`group relative flex flex-col p-8 rounded-[2rem] border transition-all duration-500 ${
                        isPopular 
                          ? 'border-blue-500/50 bg-blue-50/50 dark:bg-blue-500/5 ring-4 ring-blue-500/10' 
                          : 'border-slate-200 dark:border-white/5 bg-white dark:bg-white/[0.02] hover:border-slate-300 dark:hover:border-white/20'
                      }`}
                    >
                      {isPopular && (
                        <div className="absolute -top-4 left-1/2 -translate-x-1/2 whitespace-nowrap">
                          <span className="bg-blue-600 text-white text-[10px] font-black px-4 py-1 rounded-full uppercase tracking-[0.2em] shadow-lg shadow-blue-500/40">
                            Empfohlen
                          </span>
                        </div>
                      )}

                      <div className="flex items-center gap-4 mb-8">
                        <div className={`p-3.5 rounded-2xl ${isPopular ? 'bg-blue-600 text-white shadow-xl shadow-blue-500/20' : 'bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-300'}`}>
                          <TierIcon tier={pkg.tier} />
                        </div>
                        <div>
                          <h3 className="text-xl font-bold text-slate-900 dark:text-white">{pkg.name}</h3>
                          <p className="text-xs font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest">
                            {pkg.credits} Credits
                          </p>
                        </div>
                      </div>

                      <div className="mb-6 flex items-baseline gap-1">
                        <span className="text-5xl font-black text-slate-900 dark:text-white">
                          {pkg.currency === 'EUR' ? '€' : pkg.currency}{pkg.price}
                        </span>
                        {pkg.interval !== 'once' && (
                          <span className="text-slate-400 font-bold text-sm">/ {pkg.interval === 'month' ? 'Monat' : 'Jahr'}</span>
                        )}
                      </div>

                      <p className="text-sm font-medium leading-relaxed text-slate-500 dark:text-slate-400 mb-8 min-h-[48px]">
                        {pkg.name}
                      </p>

                      <div className="space-y-4 mb-10 flex-grow">
                        {pkg.features.map((feature, idx) => (
                          <div key={idx} className="flex items-start gap-3">
                            <div className={`mt-1 rounded-full p-0.5 ${isPopular ? 'bg-blue-500/20' : 'bg-green-500/10'}`}>
                              <Check className={`w-3.5 h-3.5 ${isPopular ? 'text-blue-500' : 'text-green-500'}`} />
                            </div>
                            <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">{feature}</span>
                          </div>
                        ))}
                      </div>

                      <button
                        type="button"
                        onClick={() => handlePurchase(pkg.id)}
                        disabled={isCurrent || isProcessing}
                        className={`relative w-full py-4 px-6 rounded-2xl font-black text-sm flex items-center justify-center gap-2 transition-all active:scale-[0.97] ${
                          isCurrent
                            ? 'bg-slate-100 dark:bg-white/5 text-slate-400 cursor-default'
                            : isPopular
                              ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/30'
                              : 'bg-slate-900 dark:bg-white hover:bg-slate-800 dark:hover:bg-slate-100 text-white dark:text-slate-900 shadow-xl'
                        }`}
                      >
                        {isLoading ? (
                          <Loader2 className="w-5 h-5 animate-spin" />
                        ) : (
                          <React.Fragment>
                            <span>{isCurrent ? 'Aktiver Plan' : 'Auswählen'}</span>
                            {!isCurrent && <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />}
                          </React.Fragment>
                        )}
                      </button>
                    </div>
                  );
                })
              )}
            </div>

            <div className="mt-16 pt-10 border-t border-slate-100 dark:border-white/5 flex flex-col md:flex-row items-center justify-between gap-8">
              <div className="flex items-center gap-10">
                <div className="space-y-1">
                  <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Sicherheit</div>
                  <div className="text-sm font-bold text-slate-600 dark:text-slate-400 flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-green-500" />
                    AES-256 Verschlüsselt
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Support</div>
                  <div className="text-sm font-bold text-slate-600 dark:text-slate-400 flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-blue-500" />
                    24/7 Priority-Chat
                  </div>
                </div>
              </div>
              <p className="text-xs font-medium text-slate-400 dark:text-slate-500 text-center md:text-right max-w-sm leading-relaxed">
                Preise inkl. MwSt. Abonnements können jederzeit in den Kontoeinstellungen gekündigt werden. Es gelten unsere AGB.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};

export default PaywallModal;