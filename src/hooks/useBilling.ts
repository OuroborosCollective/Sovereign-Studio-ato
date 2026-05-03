import { useCallback, useMemo } from 'react';
import { useAppSelector, useAppDispatch } from '../store/hooks';
import {
  selectIsSubscribed,
  selectIsLoading,
  selectBillingError,
  selectBillingPackages,
  purchasePackage,
  restorePurchases,
} from '../features/billing/billingSlice';

/**
 * Hook zur Kapselung der Paywall-Logik und In-App-Purchase Status.
 * Bietet Zugriff auf den Abonnement-Status und Kauf-Funktionen.
 */
export const useBilling = () => {
  const dispatch = useAppDispatch();

  const isSubscribed = useAppSelector(selectIsSubscribed);
  const isLoading = useAppSelector(selectIsLoading);
  const error = useAppSelector(selectBillingError);
  const packages = useAppSelector(selectBillingPackages);

  const purchase = useCallback(
    async (packageId: string) => {
      try {
        await dispatch(purchasePackage(packageId)).unwrap();
        return { success: true, error: null };
      } catch (err) {
        return { success: false, error: err };
      }
    },
    [dispatch]
  );

  const handleRestorePurchases = useCallback(async () => {
    try {
      await dispatch(restorePurchases()).unwrap();
      return { success: true, error: null };
    } catch (err) {
      return { success: false, error: err };
    }
  }, [dispatch]);

  const billingStatus = useMemo(() => ({
    isPro: isSubscribed,
    canAccessPremiumFeatures: isSubscribed,
    showPaywall: !isSubscribed && !isLoading,
  }), [isSubscribed, isLoading]);

  return {
    ...billingStatus,
    isLoading,
    error,
    packages,
    purchase,
    restorePurchases: handleRestorePurchases,
  };
};

export default useBilling;