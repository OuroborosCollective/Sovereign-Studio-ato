import type { SafetyLevel } from './predictiveSafety';

declare module '../runtime/RuntimeIntelligence' {
  interface RuntimeGuardResult {
    /**
     * Advisory risk metadata emitted by predictive guards.
     * This is telemetry/context only; hard runtime guard pass/fail remains authoritative.
     */
    riskReduction?: number;
    properties?: {
      confidence?: number;
      safety?: SafetyLevel;
      similarFailures?: number;
      warnOnly?: boolean;
      minConfidence?: number;
      healthStatus?: SafetyLevel;
      errorRate?: number;
      [key: string]: unknown;
    };
  }
}
