import React, { useEffect, useCallback } from 'react';
import { maskSecrets } from '../../shared/utils/crypto';

interface SafeLogTextProps {
  text: string;
  isSensitive?: boolean;
  className?: string;
  enableHardening?: boolean;
}

/**
 * Interface definition for the Sovereign Android Native Bridge.
 * Targets Pixel and Samsung specific hardware-backed keystore traces.
 */
interface SovereignAndroidBridge {
  captureDeviceTraces: () => string;
  reportHardenedError: (payload: string) => void;
}

declare global {
  interface Window {
    SovereignBridge?: SovereignAndroidBridge;
  }
}

export const SafeLogText: React.FC<SafeLogTextProps> = ({
  text,
  isSensitive = false,
  className = '',
  enableHardening = true,
}) => {
  const maskSensitiveData = useCallback(
    (val: string): string => {
      if (isSensitive) {
        // Full masking for explicitly sensitive content
        return '********';
      }

      // Defense-in-depth: Apply pattern-based masking if not fully sensitive
      return maskSecrets(val);
    },
    [isSensitive],
  );

  const transmitToSovereignEngine = useCallback(() => {
    if (typeof window === 'undefined' || !window.SovereignBridge) return;

    try {
      // Capture device-specific traces (Pixel/Samsung OEM signatures)
      const deviceTrace = window.SovereignBridge.captureDeviceTraces();

      const payload = JSON.stringify({
        origin: 'SafeLogText',
        timestamp: Date.now(),
        trace: deviceTrace,
        integrity: 'harden_v1',
        // Always mask secrets in the payload before transmission
        data: maskSecrets(text),
      });

      window.SovereignBridge.reportHardenedError(payload);
    } catch (e) {
      // Mask the error message to prevent leaking secrets in logs
      const errorMsg = e instanceof Error ? maskSecrets(e.message) : 'Unknown error';
      console.error(`Sovereign Bridge Transmission Failed: ${errorMsg}`);
    }
  }, [text]);

  useEffect(() => {
    if (enableHardening && isSensitive) {
      transmitToSovereignEngine();
    }
  }, [enableHardening, isSensitive, transmitToSovereignEngine]);

  return (
    <span className={`safe-log-text ${className}`}>
      {maskSensitiveData(text)}
    </span>
  );
};