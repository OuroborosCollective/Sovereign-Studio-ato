/**
 * Time Utilities - Normalized Hz-based timing system
 * 1 second = 100 Hz
 * 10 Hz = 100ms (10 ticks per second)
 * 1 Hz = 1000ms (1 tick per second)
 */

// Normalize Hz to milliseconds: 1000ms / hz
export function hzToMs(hz: number): number {
  if (hz <= 0) return 1000; // Default 1 Hz
  return Math.round(1000 / hz);
}

// Normalize milliseconds to Hz: 1000ms / ms
export function msToHz(ms: number): number {
  if (ms <= 0) return 1;
  return Math.round(1000 / ms);
}

// Common tick rates as Hz constants
export const HZ = {
  ULTRA_SLOW: 0.5,    // 2000ms - very slow monitoring (0.5 Hz)
  SLOW: 1,            // 1000ms - slow updates (1 Hz)
  NORMAL: 10,         // 100ms - normal updates (10 Hz)
  FAST: 50,            // 20ms - fast updates (50 Hz)
  ULTRA_FAST: 100,     // 10ms - very fast updates (100 Hz)
} as const;

// Pre-computed tick rates (in milliseconds)
export const TICK_RATES = {
  /** Ultra slow monitoring - 2000ms between ticks (0.5 Hz) */
  MONITOR_SLOW: hzToMs(HZ.ULTRA_SLOW),
  /** Standard interval - 1000ms between ticks (1 Hz) */
  INTERVAL_STANDARD: hzToMs(HZ.SLOW),
  /** Fast updates - 100ms between ticks (10 Hz) */
  RENDER_FAST: hzToMs(HZ.NORMAL),
  /** Coach render interval - 100ms (10 Hz) */
  COACH_RENDER: hzToMs(HZ.NORMAL),
  /** Mutation debounce - 120ms (~8 Hz) */
  MUTATION_DEBOUNCE: 120,
  /** Initial render delay - 700ms */
  INITIAL_RENDER_DELAY: 700,
} as const;

// Default tick rate for coach (10Hz = 100ms)
export const DEFAULT_TICK_HZ = HZ.NORMAL; // 10 Hz
export const DEFAULT_TICK_MS = hzToMs(DEFAULT_TICK_HZ); // 100ms
