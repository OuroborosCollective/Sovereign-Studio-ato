import React from 'react';

interface LoginViewProps {
  onLogin: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLogin }) => {
  React.useLayoutEffect(() => {
    window.setTimeout(onLogin, 0);
  }, [onLogin]);

  return (
    <main
      className="sovereign-login-shell h-[100dvh] bg-black"
      data-testid="sovereign-monitor-entry-bridge"
      data-layout="monitor-entry-bridge"
      aria-label="Sovereign Monitor wird geöffnet"
    />
  );
};
