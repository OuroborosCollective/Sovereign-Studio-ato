import { useCallback, useMemo } from 'react';
import { useAppSelector, useAppDispatch } from '../store/hooks';
import {
  selectIsSubscribed,
  selectBillingLoading,
  selectBillingError,
  selectPackages,
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
  const isLoading = useAppSelector(selectBillingLoading);
  const error = useAppSelector(selectBillingError);
  const packages = useAppSelector(selectPackages);

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

  const restore = useCallback(async () => {
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
    restorePurchases: restore,
  };
};

export default useBilling;