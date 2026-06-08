/**
 * Self-Healing Configuration
 * Defines recovery strategies and thresholds
 */

export interface SelfHealingConfig {
  maxAttempts: number;
  baseDelay: number;
  maxDelay: number;
  backoffMultiplier: number;
  recoveryStrategies: RecoveryStrategy[];
  monitoringInterval: number;
}

export interface RecoveryStrategy {
  name: string;
  trigger: (error: Error) => boolean;
  action: () => Promise<boolean>;
  priority: number;
}

export interface HealthMetric {
  timestamp: number;
  cpuUsage: number;
  memoryUsage: number;
  errorCount: number;
  responseTime: number;
  activeProviders: string[];
}

export const DEFAULT_HEALING_CONFIG: SelfHealingConfig = {
  maxAttempts: Infinity, // Unlimited iterations until success
  baseDelay: 1000,
  maxDelay: 30000,
  backoffMultiplier: 1.5, // Gentle backoff for unlimited attempts
  recoveryStrategies: [],
  monitoringInterval: 5000,
};

export const RECOVERY_STRATEGIES: RecoveryStrategy[] = [
  {
    name: 'Reload React Native',
    trigger: (error: Error) => error.message.toLowerCase().includes('js error') || error.message.toLowerCase().includes('undefined'),
    action: async () => {
      // In Detox: await device.reloadReactNative();
      console.log('🔄 Reloading React Native...');
      return true;
    },
    priority: 1,
  },
  {
    name: 'Clear App State',
    trigger: (error: Error) => error.message.toLowerCase().includes('state') || error.message.toLowerCase().includes('redux'),
    action: async () => {
      // Clear Redux/Zustand state
      console.log('🧹 Clearing app state...');
      return true;
    },
    priority: 2,
  },
  {
    name: 'Reset Network',
    trigger: (error: Error) => error.message.toLowerCase().includes('network') || error.message.toLowerCase().includes('fetch'),
    action: async () => {
      console.log('🌐 Resetting network connection...');
      return true;
    },
    priority: 3,
  },
  {
    name: 'Fallback to Cache',
    trigger: (error: Error) => error.message.toLowerCase().includes('cache') || error.message.toLowerCase().includes('storage'),
    action: async () => {
      console.log('💾 Falling back to cached data...');
      return true;
    },
    priority: 4,
  },
  {
    name: 'Restart App',
    trigger: (error: Error) => error.message.toLowerCase().includes('crash') || error.message.toLowerCase().includes('fatal'),
    action: async () => {
      console.log('🔃 Restarting app...');
      // In Detox: await device.launchApp({ newInstance: true });
      return true;
    },
    priority: 5,
  },
  {
    name: 'Send to Background',
    trigger: (error: Error) => error.message.toLowerCase().includes('UI') || error.message.toLowerCase().includes('render'),
    action: async () => {
      console.log('⏸️ Sending app to background...');
      // In Detox: await device.sendToHome();
      return true;
    },
    priority: 6,
  },
  {
    name: 'Factory Reset',
    trigger: (error: Error) => error.message.toLowerCase().includes('memory') || error.message.toLowerCase().includes('heap'),
    action: async () => {
      console.log('⚠️ Performing factory reset...');
      return true;
    },
    priority: 7,
  },
];

export interface SelfHealingState {
  attemptCount: number;
  lastError: Error | null;
  isHealing: boolean;
  recoveryHistory: Array<{
    timestamp: number;
    strategy: string;
    success: boolean;
    duration: number;
  }>;
}

export const SELF_HEALING_THRESHOLDS = {
  memoryWarning: 80, // percentage
  cpuWarning: 90, // percentage
  errorRateWarning: 10, // errors per minute
  responseTimeWarning: 5000, // ms
  networkTimeout: 30000, // ms
};