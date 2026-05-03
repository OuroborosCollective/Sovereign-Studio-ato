import { useCallback, useMemo } from 'react';
import { useAppDispatch, useAppSelector } from '../store/hooks';
import {
  selectIsSubscribed,
  selectIsLoading,
  selectBillingError,
  selectAvailablePackages,
  purchasePackageAction,
  restorePurchasesAction,
} from '../store/slices/billingSlice';

/**
 * Hook zur Kapselung der Paywall-Logik und In-App-Purchase Status.
 * Nutzt typed Hooks für Redux (useAppDispatch, useAppSelector).
 */
export const useBilling = () => {
  const dispatch = useAppDispatch();

  const isSubscribed = useAppSelector(selectIsSubscribed);
  const isLoading = useAppSelector(selectIsLoading);
  const error = useAppSelector(selectBillingError);
  const packages = useAppSelector(selectAvailablePackages);

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