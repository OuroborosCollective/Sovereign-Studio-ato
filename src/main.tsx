import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';

/**
 * Sovereign Studio v3 - Refactor Edition
 * 
 * Main feature: AI-powered code refactoring
 * Optional API keys for enhanced capabilities
 * Works for free with mlvoca (no key needed)
 */

// Polyfills for older browsers/compatibility
if (typeof window !== 'undefined') {
  (window as any).global = window;

  (window as any).requestIdleCallback = window.requestIdleCallback || ((cb: any) => {
    const start = Date.now();
    return setTimeout(() => {
      cb({
        didTimeout: false,
        timeRemaining: () => Math.max(0, 50 - (Date.now() - start)),
      });
    }, 1);
  });

  // Performance optimization
  const style = document.createElement('style');
  style.textContent = 'canvas { will-change: transform; transform: translateZ(0); } .ai-stream-container { contain: content; }';
  document.head.appendChild(style);
}

// Initialize PostHog if key is provided
const posthogKey = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
const posthogHost = (import.meta.env.VITE_POSTHOG_HOST as string | undefined) ?? 'https://eu.i.posthog.com';

if (posthogKey) {
  try {
    posthog.init(posthogKey, {
      api_host: posthogHost,
      person_profiles: 'identified_only',
    });
  } catch (e) {
    console.warn('PostHog init failed:', e);
  }
}

// Initialize Google Auth if configured (non-blocking)
const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
if (googleClientId) {
  import('@codetrix-studio/capacitor-google-auth')
    .then(({ GoogleAuth }) => {
      try {
        GoogleAuth.initialize({
          clientId: googleClientId,
          scopes: ['profile', 'email'],
          grantOfflineAccess: true,
        });
      } catch (err: unknown) {
        console.warn('GoogleAuth init failed:', err);
      }
    })
    .catch(() => {
      // Ignore - Google Auth is optional
    });
}

// Render app
const container = document.getElementById('root');

if (container) {
  // Dynamic import App to ensure all dependencies are loaded
  import('./App').then(({ default: App }) => {
    const root = createRoot(container);
    root.render(
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    );
  }).catch((err) => {
    console.error('Failed to load App:', err);
    const errorDiv = document.createElement('div');
    errorDiv.style.color = 'white';
    errorDiv.style.padding = '20px';
    errorDiv.textContent = 'Failed to load application. Please refresh.';
    container.replaceChildren(errorDiv);
  });
}