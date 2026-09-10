import react from '@vitejs/plugin-react';
import path from 'path';
import { readFileSync } from 'node:fs';
import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(() => {
  const enableSourcemaps = process.env.VITE_BUILD_SOURCEMAP === 'true';
  const e2eBackendProxyTarget = process.env.SOVEREIGN_E2E_BACKEND_PROXY_TARGET?.trim();
  const liveFivePath = process.env.SOVEREIGN_E2E_LIVE === '1';
  const tlsCert = process.env.SOVEREIGN_E2E_TLS_CERT?.trim();
  const tlsKey = process.env.SOVEREIGN_E2E_TLS_KEY?.trim();
  if (liveFivePath && (!e2eBackendProxyTarget || !tlsCert || !tlsKey)) {
    throw new Error('LIVE_PREVIEW_TLS_CONFIGURATION_REQUIRED');
  }

  return {
    base: './',
    plugins: [
      react(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './'),
      },
    },
    preview: e2eBackendProxyTarget ? {
      host: '127.0.0.1',
      port: 3000,
      strictPort: true,
      https: liveFivePath && tlsCert && tlsKey
        ? { cert: readFileSync(tlsCert), key: readFileSync(tlsKey) }
        : undefined,
      proxy: {
        '/api': {
          target: e2eBackendProxyTarget,
          changeOrigin: true,
          secure: true,
          cookieDomainRewrite: '127.0.0.1',
        },
      },
    } : undefined,
    server: {
      host: '0.0.0.0',
      port: 5000,
      strictPort: true,
      allowedHosts: true,
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modify—file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      watch: {
        // Prevent excessive polling in containerized/orchestrated environments
        usePolling: true,
        interval: 1000,
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      sourcemap: enableSourcemaps,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules')) {
              if (id.includes('react') || id.includes('react-dom')) {
                return 'vendor';
              }
              return 'dependencies';
            }
          },
        },
      },
    },
  };
});
