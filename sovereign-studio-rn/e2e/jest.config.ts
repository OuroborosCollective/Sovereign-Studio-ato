/**
 * Jest Configuration for E2E Tests
 * Configures all test suites: API Fallback, Self-Healing, Workflows
 */

export default {
  preset: 'react-native',
  testEnvironment: 'node',
  testMatch: [
    '**/e2e/**/*.spec.ts',
    '**/e2e/**/*.test.ts',
  ],
  transform: {
    '^.+\\.tsx?$': [
      'ts-jest',
      {
        tsconfig: 'tsconfig.json',
        useESM: true,
      },
    ],
  },
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/index.ts',
  ],
  coverageThreshold: {
    global: {
      branches: 50,
      functions: 50,
      lines: 50,
      statements: 50,
    },
  },
  testTimeout: 120000,
  verbose: true,
  colors: true,
  reporters: [
    'default',
    ['jest-junit', {
      outputDirectory: './test-results',
      outputName: 'junit.xml',
      classNameTemplate: '{filepath}',
      titleTemplate: '{title}',
      ancestorSeparator: ' > ',
      usePathForSuiteName: true,
    }],
  ],
  setupFilesAfterEnv: [],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
};