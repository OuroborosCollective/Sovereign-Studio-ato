import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react() as any],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
    include: [
      'src/**/*.{test,spec}.{ts,tsx}',
      'sovereign-studio-rn/e2e/workflows/*.spec.ts',
      'sovereign-studio-rn/e2e/api-fallback/*.spec.ts',
      'sovereign-studio-rn/e2e/self-healing/*.spec.ts'
    ],
  },
});
