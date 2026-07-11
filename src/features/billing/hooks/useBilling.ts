import { useEffect, useMemo } from 'react';
import { useAppDispatch, useAppSelector } from '../../../store/hooks';
import {
  fetchBillingData,
  fetchEnabledPaymentMethods,
  purchasePackage,
  cancelSubscription as cancelSubAction,
  selectSubscription,
  selectInvoices,
  selectIsLoading,
  selectBillingError,
  selectPackages,
  selectPaymentMethods,
  type PurchaseArgs,
  type PurchaseResult,
} from '../billingSlice';

export const useBilling = () => {
  const dispatch = useAppDispatch();
  const subscription = useAppSelector(selectSubscription);
  const invoices = useAppSelector(selectInvoices);
  const loading = useAppSelector(selectIsLoading);
  const error = useAppSelector(selectBillingError);
  const packages = useAppSelector(selectPackages);
  const paymentMethods = useAppSelector(selectPaymentMethods);

  useEffect(() => {
    void dispatch(fetchBillingData());
    void dispatch(fetchEnabledPaymentMethods());
  }, [dispatch]);

  const purchase = async (args: string | PurchaseArgs): Promise<PurchaseResult> => {
    const result = await dispatch(purchasePackage(args)).unwrap();
    await dispatch(fetchBillingData()).unwrap();
    return result;
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
    paymentMethods,
    refresh: () => dispatch(fetchBillingData()),
    purchase,
    updateSubscription,
    cancelSubscription,
  };
};
