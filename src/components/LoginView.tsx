import React from 'react';

interface LoginViewProps {
  onLogin: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLogin }) => {
  return (
    <div className="p-6">
      <button onClick={onLogin}>Login</button>
    </div>
  );
};
