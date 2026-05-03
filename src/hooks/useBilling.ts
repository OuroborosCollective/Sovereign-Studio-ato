import { useSelector, useDispatch } from 'react-redux';
import { useCallback, useMemo } from 'react';
import {
  selectIsSubscribed,
  selectIsLoading,
  selectBillingError,
  selectAvailablePackages,
  purchasePackageAction,
  restorePurchasesAction,
} from '../features/billing/billingSlice';

/**
 * Hook zur Kapselung der Paywall-Logik und In-App-Purchase Status.
 * Bietet Zugriff auf den Abonnement-Status und Kauf-Funktionen.
 */
export const useBilling = () => {
  const dispatch = useDispatch();

  const isSubscribed = useSelector(selectIsSubscribed);
  const isLoading = useSelector(selectIsLoading);
  const error = useSelector(selectBillingError);
  const packages = useSelector(selectAvailablePackages);

  const purchase = useCallback(
    async (packageId: string) => {
      try {
        await dispatch(purchasePackageAction(packageId)).unwrap();
        return { success: true, error: null };
      } catch (err) {
        return { success: false, error: err };
      }
    },
    [dispatch]
  );

  const restorePurchases = useCallback(async () => {
    try {
      await dispatch(restorePurchasesAction()).unwrap();
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
    restorePurchases,
  };
};

export default useBilling;