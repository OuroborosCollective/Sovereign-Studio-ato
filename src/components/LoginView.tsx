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
      data-testid="sovereign-chat-entry-bridge"
      data-layout="chat-entry-bridge"
      aria-label="Sovereign Chat wird geöffnet"
    />
  );
};
