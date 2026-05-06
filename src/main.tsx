import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import { GoogleAuth } from '@codetrix-studio/capacitor-google-auth';
import ProductMagicApp from './ProductMagicApp';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';

/**
 * Global Polyfills and Performance Optimizations for Sovereign Studio V3.
 * Optimiert für WebView-Performance und stabile Canvas-Interaktionen in Android/Hybrid-Umgebungen.
 */
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

  const style = document.createElement('style');
  style.innerHTML = `
    canvas { will-change: transform; transform: translateZ(0); } 
    .ai-stream-container { contain: content; }
    #root { height: 100%; width: 100%; overflow: hidden; }
  `;
  document.head.appendChild(style);
}

/**
 * Analytics Initialisierung (PostHog)
 */
const posthogKey = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
const posthogHost = (import.meta.env.VITE_POSTHOG_HOST as string | undefined) ?? 'https://eu.i.posthog.com';

if (posthogKey) {
  posthog.init(posthogKey, {
    api_host: posthogHost,
    person_profiles: 'identified_only',
    capture_pageview: true,
    persistence: 'localStorage'
  });
}

/**
 * Native Google Auth Initialisierung für Capacitor 6
 */
const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;

if (googleClientId) {
  GoogleAuth.initialize({
    clientId: googleClientId,
    scopes: ['profile', 'email'],
    grantOfflineAccess: true,
  }).catch(err => {
    console.error('GoogleAuth Initialization failed:', err);
  });
}

/**
 * Robuste Root-Initialisierung
 * Stellt sicher, dass das DOM-Element existiert, bevor die React-App gerendert wird.
 */
const initApp = () => {
  const container = document.getElementById('root');

  if (!container) {
    const errorMsg = "Critical Error: Root element '#root' not found. Ensure index.html is correct.";
    console.error(errorMsg);
    const fallback = document.createElement('div');
    fallback.style.color = 'white';
    fallback.style.background = 'red';
    fallback.style.padding = '20px';
    fallback.innerText = errorMsg;
    document.body.appendChild(fallback);
    return;
  }

  try {
    const root = createRoot(container);
    root.render(
      <StrictMode>
        <ErrorBoundary>
          <ProductMagicApp />
        </ErrorBoundary>
      </StrictMode>
    );
  } catch (err) {
    console.error('Failed to render React root:', err);
  }
};

// Start der Applikation
initApp();