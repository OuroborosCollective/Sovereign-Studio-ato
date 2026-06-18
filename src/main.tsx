import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './runtime-adapter';
import './index.css';

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
  style.textContent = [
    'canvas { will-change: transform; transform: translateZ(0); }',
    '.ai-stream-container { contain: content; }',
    '@media (orientation: landscape) { #root > div.min-h-screen > div:nth-of-type(1) button { flex: 0 0 clamp(5.35rem, 12vw, 8rem); } }',
  ].join(' ');
  document.head.appendChild(style);
}

const posthogKey = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
const posthogHost = (import.meta.env.VITE_POSTHOG_HOST as string | undefined) ?? 'https://eu.i.posthog.com';
if (posthogKey) {
  try {
    posthog.init(posthogKey, {
      api_host: posthogHost,
      person_profiles: 'identified_only',
    });
  } catch (error) {
    console.warn('PostHog init failed:', error);
  }
}

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
      } catch (error) {
        console.warn('GoogleAuth init failed:', error);
      }
    })
    .catch(() => undefined);
}

const container = document.getElementById('root');
if (container) {
  const root = createRoot(container);
  root.render(
    <StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </StrictMode>
  );
}
