import React from 'react';
export const PaywallModal = ({ show, onClose, onUpgrade }: any) => {
  if (!show) return null;
  return <div>Paywall</div>;
};
