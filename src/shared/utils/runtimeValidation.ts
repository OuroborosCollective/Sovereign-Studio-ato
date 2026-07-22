// Runtime Validation System for Sovereign Studio
// Provides comprehensive validation at runtime to catch issues early
//
// This system ensures:
// - No invalid state reaches production
// - All API calls have proper fallback
// - All user inputs are validated before use
// - All routes have proper error handling

// Validation result type
export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  /** Compatibility alias for older call sites that read a single error string. */
  error?: string;
}

// Global runtime validation mode - set to true for strict mode
const RUNTIME_STRICT_MODE = true;

/**
 * Validates that a value is not null or undefined
 */
export function validateRequired<T>(value: T | null | undefined, fieldName: string): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (value === null || value === undefined) {
    errors.push(`[VALIDATION] Required field '${fieldName}' is null or undefined`);
  }

  return { valid: errors.length === 0, errors, warnings, error: errors[0] };
}

/**
 * Validates that a string is not empty
 */
export function validateNonEmpty(value: string | undefined | null, fieldName: string): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!value || value.trim().length === 0) {
    errors.push(`[VALIDATION] Field '${fieldName}' cannot be empty`);
  }

  return { valid: errors.length === 0, errors, warnings, error: errors[0] };
}

/**
 * Validates URL format
 */
export function validateUrl(url: string, fieldName: string): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  try {
    new URL(url);
  } catch {
    errors.push(`[VALIDATION] Field '${fieldName}' is not a valid URL: ${url}`);
  }

  return { valid: errors.length === 0, errors, warnings, error: errors[0] };
}

// Hoisted regular expressions to avoid redundant object recreation and recompilation.
const GITHUB_URL_PATTERN = /^(https?:\/\/)?(www\.)?github\.com\/[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}\/[a-zA-Z0-9._-]+(?:\.git)?\/?(?:tree\/[A-Za-z0-9._\/-]+)?\/?$/;
const WHITESPACE_PATTERN = /\s/;
const KNOWN_GITHUB_TOKEN_PATTERN = /^(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{30,255}$|^github_pat_[A-Za-z0-9_]{22}_[A-Za-z0-9_]{59,255}$/;

/**
 * Validates GitHub repository URL format.
 * Supports normal repo URLs and optional /tree/<branch> URLs used by the UI parser.
 */
export function validateGitHubUrl(url: string, fieldName: string = 'repoUrl'): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  const trimmed = url.trim();

  if (!GITHUB_URL_PATTERN.test(trimmed)) {
    errors.push(`[VALIDATION] Field '${fieldName}' is not a valid GitHub URL: ${url}`);
  }

  return { valid: errors.length === 0, errors, warnings, error: errors[0] };
}

/**
 * Validates API key format (basic validation)
 */
export function validateApiKey(key: string | undefined | null, fieldName: string): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (key && key.trim().length > 0) {
    if (key.length < 10) {
      warnings.push(`[VALIDATION] Field '${fieldName}' appears to be too short`);
    }
    // Check for common patterns
    if (key.startsWith('ghp_') && key.length < 30) {
      errors.push(`[VALIDATION] Field '${fieldName}' appears to be an invalid GitHub PAT (too short)`);
    }
  }

  return { valid: errors.length === 0, errors, warnings, error: errors[0] };
}

/**
 * Validates GitHub token format without contacting GitHub.
 * This is a structural runtime check only; it never proves account validity or scopes.
 */
export function validateGitHubToken(token: string | undefined | null, fieldName: string = 'githubToken'): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  const value = token?.trim() ?? '';

  if (value.length === 0) {
    return { valid: true, errors, warnings, error: errors[0] };
  }

  if (WHITESPACE_PATTERN.test(value)) {
    errors.push(`[VALIDATION] Field '${fieldName}' must not contain whitespace`);
  }

  if (!KNOWN_GITHUB_TOKEN_PATTERN.test(value)) {
    warnings.push(`[VALIDATION] Field '${fieldName}' does not match a known GitHub token prefix/shape`);
  }

  if (value.length < 30) {
    errors.push(`[VALIDATION] Field '${fieldName}' appears to be too short for a GitHub token`);
  }

  return { valid: errors.length === 0, errors, warnings, error: errors[0] };
}

/**
 * Validates a number is within bounds
 */
export function validateNumberBounds(value: number, min: number, max: number, fieldName: string): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (value < min || value > max) {
    errors.push(`[VALIDATION] Field '${fieldName}' value ${value} is outside bounds [${min}, ${max}]`);
  }

  return { valid: errors.length === 0, errors, warnings, error: errors[0] };
}

/**
 * Validates an array is not empty
 */
export function validateArrayNotEmpty<T>(arr: T[] | undefined | null, fieldName: string): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!arr || arr.length === 0) {
    errors.push(`[VALIDATION] Field '${fieldName}' array is empty or undefined`);
  }

  return { valid: errors.length === 0, errors, warnings, error: errors[0] };
}

/**
 * Combines multiple validation results
 */
export function combineValidationResults(...results: ValidationResult[]): ValidationResult {
  const allErrors = results.flatMap(r => r.errors);
  const allWarnings = results.flatMap(r => r.warnings);

  return {
    valid: allErrors.length === 0,
    errors: allErrors,
    warnings: allWarnings,
    error: allErrors[0],
  };
}

/**
 * Validates the entire application state
 */
export function validateAppState(state: {
  repoUrl?: string;
  accessKey?: string;
  geminiKey?: string;
  cards?: unknown[];
  settings?: {
    repoMode?: string;
    packageManager?: string;
    linter?: string;
  };
}): ValidationResult {
  const results: ValidationResult[] = [];

  // Validate repo URL if provided
  if (state.repoUrl) {
    results.push(validateGitHubUrl(state.repoUrl, 'repoUrl'));
  }

  // Validate API keys
  if (state.accessKey) {
    results.push(validateGitHubToken(state.accessKey, 'accessKey'));
  }
  if (state.geminiKey) {
    results.push(validateApiKey(state.geminiKey, 'geminiKey'));
  }

  // Validate cards array
  if (state.cards !== undefined) {
    results.push(validateArrayNotEmpty(state.cards, 'cards'));
  }

  // Validate settings
  if (state.settings) {
    if (state.settings.repoMode) {
      const validModes = ['monorepo', 'single'];
      if (!validModes.includes(state.settings.repoMode)) {
        results.push({
          valid: false,
          errors: [`[VALIDATION] Invalid repoMode: ${state.settings.repoMode}`],
          warnings: [],
          error: `[VALIDATION] Invalid repoMode: ${state.settings.repoMode}`,
        });
      }
    }
    if (state.settings.packageManager) {
      const validManagers = ['auto', 'pnpm', 'npm', 'yarn'];
      if (!validManagers.includes(state.settings.packageManager)) {
        results.push({
          valid: false,
          errors: [`[VALIDATION] Invalid packageManager: ${state.settings.packageManager}`],
          warnings: [],
          error: `[VALIDATION] Invalid packageManager: ${state.settings.packageManager}`,
        });
      }
    }
  }

  return combineValidationResults(...results);
}

/**
 * Runtime check that throws if condition is not met
 */
export function runtimeCheck(condition: boolean, message: string): asserts condition {
  if (!condition) {
    console.error(`[RUNTIME_CHECK_FAILED] ${message}`);
    throw new Error(`[RUNTIME_CHECK_FAILED] ${message}`);
  }
}

/**
 * Validated version of validateAppState that throws in strict mode
 */
export function validateAppStateStrict(state: {
  repoUrl?: string;
  accessKey?: string;
  geminiKey?: string;
  cards?: unknown[];
  settings?: {
    repoMode?: string;
    packageManager?: string;
    linter?: string;
  };
}): ValidationResult {
  const result = validateAppState(state);

  if (RUNTIME_STRICT_MODE && !result.valid) {
    const errorMsg = `[RUNTIME_VALIDATION_STRICT] Critical validation failed: ${result.errors.join(', ')}`;
    console.error(errorMsg);
    throw new Error(errorMsg);
  }

  return result;
}

/**
 * Safe JSON parse with fallback
 */
export function safeJsonParse<T>(json: string, fallback: T): T {
  try {
    return JSON.parse(json) as T;
  } catch (error) {
    console.warn('[SAFE_JSON_PARSE] Failed to parse JSON, using fallback:', error);
    return fallback;
  }
}

/**
 * Safe array access with bounds checking
 */
export function safeArrayAccess<T>(arr: T[], index: number, fallback: T): T {
  if (index < 0 || index >= arr.length) {
    console.warn(`[SAFE_ARRAY_ACCESS] Index ${index} out of bounds for array of length ${arr.length}`);
    return fallback;
  }
  return arr[index];
}

/**
 * Safe object property access
 */
export function safeGet<T>(obj: Record<string, T> | null | undefined, key: string, fallback: T): T {
  if (!obj) {
    console.warn(`[SAFE_GET] Object is null/undefined, cannot access key '${key}'`);
    return fallback;
  }
  return obj[key] ?? fallback;
}
