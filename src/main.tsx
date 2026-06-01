import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import { GoogleAuth } from '@codetrix-studio/capacitor-google-auth';
import { RefactorProvider } from './features/ai/RefactorContext';
import { RefactorPanel } from './features/ai/RefactorPanel';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';

/**
 * Sovereign Studio v3 - Refactor Edition
 * 
 * Main feature: AI-powered code refactoring
 * Optional API keys for enhanced capabilities
 * Works for free with mlvoca (no key needed)
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
  style.innerHTML = 'canvas { will-change: transform; transform: translateZ(0); } .ai-stream-container { contain: content; }';
  document.head.appendChild(style);
}

const posthogKey = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
const posthogHost = (import.meta.env.VITE_POSTHOG_HOST as string | undefined) ?? 'https://eu.i.posthog.com';

if (posthogKey) {
  posthog.init(posthogKey, {
    api_host: posthogHost,
    person_profiles: 'identified_only',
  });
}

const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;

const initAndRender = async () => {
  if (googleClientId) {
    try {
      await GoogleAuth.initialize({
        clientId: googleClientId,
        scopes: ['profile', 'email'],
        grantOfflineAccess: true,
      });
    } catch (error) {
      console.error('GoogleAuth initialization failed', error);
    }
  }

  const container = document.getElementById('root');

  if (container) {
    const root = createRoot(container);
    root.render(
      <StrictMode>
        <ErrorBoundary>
          <RefactorProvider>
            <RefactorPanel />
          </RefactorProvider>
        </ErrorBoundary>
      </StrictMode>
    );
  }
};

initAndRender();