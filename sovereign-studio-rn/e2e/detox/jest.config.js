/**
 * Jest Configuration for Detox E2E Tests
 */

module.exports = {
  preset: 'react-native',
  testEnvironment: 'node',
  testMatch: ['**/e2e/detox/**/*.spec.ts'],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', { tsconfig: 'tsconfig.json' }],
  },
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],
  testTimeout: 120000,
  verbose: true,
  colors: true,
  reporters: [
    'default',
    ['jest-junit', {
      outputDirectory: './test-results/detox',
      outputName: 'detox-results.xml',
    }],
  ],
  setupFilesAfterEnv: [],
};