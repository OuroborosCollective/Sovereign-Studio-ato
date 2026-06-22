import type { UserApiKeys } from '../components/UserKeyManager';

export type ProviderKeyValidationCode =
  | 'valid'
  | 'empty'
  | 'invalid_format'
  | 'invalid_prefix'
  | 'too_short';

export interface ProviderKeyValidation {
  providerId: string;
  code: ProviderKeyValidationCode;
  message: string;
  isValid: boolean;
}

export interface ProviderKeyValidationReport {
  validations: ProviderKeyValidation[];
  validCount: number;
  invalidCount: number;
  allValid: boolean;
  validProviders: string[];
  invalidProviders: string[];
}

const KEY_PATTERNS: Record<string, { pattern: RegExp; prefix: string; minLength: number }> = {
  pollinations: {
    pattern: /^pollinations_[a-zA-Z0-9]+$/,
    prefix: 'pollinations_',
    minLength: 15,
  },
  groq: {
    pattern: /^gsk_[a-zA-Z0-9]+$/,
    prefix: 'gsk_',
    minLength: 20,
  },
  huggingface: {
    pattern: /^hf_[a-zA-Z0-9]+$/,
    prefix: 'hf_',
    minLength: 10,
  },
  together: {
    pattern: /^together_[a-zA-Z0-9]+$/,
    prefix: 'together_',
    minLength: 15,
  },
  openrouter: {
    pattern: /^sk-or-v1-[a-zA-Z0-9_-]+$/,
    prefix: 'sk-or-v1-',
    minLength: 30,
  },
  gemini: {
    pattern: /^AIza[a-zA-Z0-9_-]+$/,
    prefix: 'AIza',
    minLength: 30,
  },
};

export function validateProviderKey(providerId: string, key: string | undefined): ProviderKeyValidation {
  if (!key || key.trim() === '') {
    return {
      providerId,
      code: 'empty',
      message: `${providerId}: No key provided (will use free-tier)`,
      isValid: false,
    };
  }

  const trimmedKey = key.trim();
  const pattern = KEY_PATTERNS[providerId];

  if (!pattern) {
    return {
      providerId,
      code: 'valid',
      message: `${providerId}: Key provided (format not validated)`,
      isValid: true,
    };
  }

  if (!trimmedKey.startsWith(pattern.prefix)) {
    return {
      providerId,
      code: 'invalid_prefix',
      message: `${providerId}: Invalid prefix (expected ${pattern.prefix})`,
      isValid: false,
    };
  }

  if (trimmedKey.length < pattern.minLength) {
    return {
      providerId,
      code: 'invalid_format',
      message: `${providerId}: Key too short (min ${pattern.minLength} chars)`,
      isValid: false,
    };
  }

  if (!pattern.pattern.test(trimmedKey)) {
    return {
      providerId,
      code: 'invalid_format',
      message: `${providerId}: Invalid key format`,
      isValid: false,
    };
  }

  return {
    providerId,
    code: 'valid',
    message: `${providerId}: Key validated successfully`,
    isValid: true,
  };
}

export function validateUserApiKeys(keys: UserApiKeys): ProviderKeyValidationReport {
  const validations: ProviderKeyValidation[] = [];
  const validProviders: string[] = [];
  const invalidProviders: string[] = [];

  const providerIds = [
    'pollinations',
    'groq',
    'huggingface',
    'together',
    'openrouter',
    'gemini',
  ] as const;

  for (const providerId of providerIds) {
    const key = keys[providerId];
    const validation = validateProviderKey(providerId, key);
    validations.push(validation);

    if (validation.isValid) {
      validProviders.push(providerId);
    } else if (validation.code !== 'empty') {
      invalidProviders.push(providerId);
    }
  }

  return {
    validations,
    validCount: validProviders.length,
    invalidCount: invalidProviders.length,
    allValid: invalidProviders.length === 0,
    validProviders,
    invalidProviders,
  };
}

export function getValidatedKeys(keys: UserApiKeys): UserApiKeys {
  const report = validateUserApiKeys(keys);
  const validated: UserApiKeys = {};

  for (const validProvider of report.validProviders) {
    const key = keys[validProvider as keyof UserApiKeys];
    if (key) {
      (validated as Record<string, string>)[validProvider] = key;
    }
  }

  return validated;
}

export function shouldUseProvider(providerId: string, keys: UserApiKeys): boolean {
  const validation = validateProviderKey(providerId, keys[providerId as keyof UserApiKeys]);
  return validation.isValid;
}
