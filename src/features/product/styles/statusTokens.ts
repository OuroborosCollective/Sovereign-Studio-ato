/**
 * Status UI tokens (Issue #1567, findings E4/B3)
 *
 * - STATUS_FONT_SIZE_MIN: essential status/log text must never drop below 12px
 *   (mobile readability).
 * - Tone labels/icons: state must never be conveyed by color alone; every
 *   status affordance needs an accessible text alternative.
 * - Red (error color) is reserved exclusively for error/failure/critical.
 */

export const STATUS_FONT_SIZE_MIN = 12;

export type StatusToneLabelKey = 'neutral' | 'positive' | 'warning' | 'error';

export const STATUS_TONE_LABEL: Record<StatusToneLabelKey, string> = {
  neutral: 'Neutral',
  positive: 'OK',
  warning: 'Warnung',
  error: 'Fehler',
};

export const STATUS_TONE_ICON: Record<StatusToneLabelKey, string> = {
  neutral: '○',
  positive: '✓',
  warning: '⚠',
  error: '✕',
};

export type LogLevelLabelKey = 'info' | 'success' | 'warning' | 'error';

export const LOG_LEVEL_LABEL: Record<LogLevelLabelKey, string> = {
  info: 'Info',
  success: 'Erfolg',
  warning: 'Warnung',
  error: 'Fehler',
};

export const LOG_LEVEL_ICON: Record<LogLevelLabelKey, string> = {
  info: 'ℹ',
  success: '✓',
  warning: '⚠',
  error: '✕',
};
