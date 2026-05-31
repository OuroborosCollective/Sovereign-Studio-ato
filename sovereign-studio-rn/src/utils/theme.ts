// Matrix-style theme colors for Sovereign Studio
// Dark cyberpunk aesthetic with emerald green accents

export const Colors = {
  // Background colors
  background: '#0a0a0a',
  backgroundSecondary: '#111111',
  backgroundTertiary: '#1a1a1a',
  backgroundElevated: '#0f0f0f',

  // Surface colors
  surface: '#141414',
  surfaceHover: '#1f1f1f',
  surfaceActive: '#252525',
  surfaceBorder: '#2a2a2a',

  // Primary - Matrix Emerald Green
  primary: '#10b981',
  primaryLight: '#34d399',
  primaryDark: '#059669',
  primaryGlow: 'rgba(16, 185, 129, 0.3)',

  // Accent colors
  accent: '#8b5cf6', // Purple
  accentLight: '#a78bfa',
  
  warning: '#f59e0b', // Amber
  error: '#ef4444',   // Red
  success: '#22c55e', // Green

  // Text colors
  textPrimary: '#e5e5e5',
  textSecondary: '#a3a3a3',
  textMuted: '#6b6b6b',
  textDisabled: '#404040',

  // Matrix specific
  matrixGreen: '#00ff41',
  matrixGreenDark: '#009f2f',
  matrixGlow: 'rgba(0, 255, 65, 0.4)',

  // Status colors
  online: '#22c55e',
  busy: '#f59e0b',
  offline: '#6b7280',

  // Border colors
  border: '#2a2a2a',
  borderLight: '#3a3a3a',
  borderFocus: '#10b981',

  // Code colors
  codeBackground: '#0d0d0d',
  codeBorder: '#1e1e1e',

  // Glass effect
  glass: 'rgba(20, 20, 20, 0.8)',
  glassBorder: 'rgba(255, 255, 255, 0.05)',
};

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const BorderRadius = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  full: 9999,
};

export const FontSize = {
  xs: 10,
  sm: 12,
  md: 14,
  lg: 16,
  xl: 18,
  xxl: 24,
  xxxl: 32,
};

export const FontWeight = {
  normal: '400' as const,
  medium: '500' as const,
  semibold: '600' as const,
  bold: '700' as const,
};

// Matrix-style shadow effects
export const Shadows = {
  glow: {
    shadowColor: '#10b981',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 10,
    elevation: 5,
  },
  glowStrong: {
    shadowColor: '#10b981',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 20,
    elevation: 10,
  },
  card: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  elevated: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 8,
  },
};

// Common styles
export const CommonStyles = {
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
  },
  button: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
  },
  buttonOutline: {
    backgroundColor: 'transparent',
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.primary,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
  },
  input: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    color: Colors.textPrimary,
    fontSize: FontSize.md,
  },
  inputFocused: {
    borderColor: Colors.primary,
  },
  text: {
    color: Colors.textPrimary,
    fontSize: FontSize.md,
  },
  textSecondary: {
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
  },
};