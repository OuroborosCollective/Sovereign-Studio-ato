import { defineConfig, configDefaults } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react() as any],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
    exclude: [
      ...configDefaults.exclude, 
      'sovereign-studio-rn/e2e/detox/**',
      'sovereign-studio-rn/e2e/ki-coach/real-smoke.spec.ts',
      'tests/e2e/**',
      'backend/tests/e2e/**',
    ],
  },
});
