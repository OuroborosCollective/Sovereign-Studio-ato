module.exports = {
  displayName: 'File Creation Validation',
  testEnvironment: 'node',
  testMatch: ['**/file-creation.test.js'],
  collectCoverageFrom: [
    'src/**/*.{js,ts}',
    '!src/**/*.d.ts',
  ],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testTimeout: 30000,
  verbose: true,
  bail: false,
  errorOnDeprecated: true,
};
