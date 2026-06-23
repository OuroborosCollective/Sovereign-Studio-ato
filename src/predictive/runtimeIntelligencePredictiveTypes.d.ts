import '../runtime/RuntimeIntelligence';

declare module '../runtime/RuntimeIntelligence' {
  interface RuntimeGuardResult {
    riskReduction?: number;
    properties?: Record<string, unknown>;
  }
}
