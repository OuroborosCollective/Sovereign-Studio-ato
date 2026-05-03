import React from 'react';

interface SafeLogTextProps {
  text: string;
  isSensitive?: boolean;
  className?: string;
}

export const SafeLogText: React.FC<SafeLogTextProps> = ({ 
  text, 
  isSensitive = false, 
  className = '' 
}) => {
  const maskSensitiveData = (val: string): string => {
    if (!isSensitive) return val;
    return '********';
  };

  return (
    <span className={`safe-log-text ${className}`}>
      {maskSensitiveData(text)}
    </span>
  );
};