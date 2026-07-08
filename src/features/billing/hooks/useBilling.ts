import { useEffect, useMemo } from 'react';
import { useAppDispatch, useAppSelector } from '../../../store/hooks';
import {
  fetchBillingData,
  purchasePackage,
  cancelSubscription as cancelSubAction,
  selectSubscription,
  selectInvoices,
  selectIsLoading,
  selectBillingError,
  selectPackages,
} from '../billingSlice';

export const useBilling = () => {
  const dispatch = useAppDispatch();
  const subscription = useAppSelector(selectSubscription);
  const invoices = useAppSelector(selectInvoices);
  const loading = useAppSelector(selectIsLoading);
  const error = useAppSelector(selectBillingError);
  const packages = useAppSelector(selectPackages);

  useEffect(() => {
    dispatch(fetchBillingData());
  }, [dispatch]);

  const purchase = async (planId: string) => {
    await dispatch(purchasePackage(planId)).unwrap();
    await dispatch(fetchBillingData()).unwrap();
  };

  const updateSubscription = async (planId: string) => {
    // Falls das separate Backend-Logik erfordert, ansonsten purchase() wiederverwenden
    await dispatch(purchasePackage(planId)).unwrap();
    await dispatch(fetchBillingData()).unwrap();
  };

  const cancelSubscription = async () => {
    await dispatch(cancelSubAction()).unwrap();
    await dispatch(fetchBillingData()).unwrap();
  };

  const currentPlanId = useMemo(() => subscription?.planId ?? null, [subscription]);

  return {
    subscription,
    invoices,
    loading,
    error,
    isProcessing: loading,
    currentPlanId,
    packages,
    refresh: () => dispatch(fetchBillingData()),
    purchase,
    updateSubscription,
    cancelSubscription,
  };
};
