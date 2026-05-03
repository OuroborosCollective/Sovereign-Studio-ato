import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import { GoogleAuth } from '@codetrix-studio/capacitor-google-auth';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';

/**
 * Global Polyfills and Performance Optimizations
 * Target: Webview Performance and AI Streaming Stability
 */
if (typeof window !== 'undefined') {
  // Global reference for compatibility with various libraries
  (window as any).global = window;

  // Polyfill requestIdleCallback for background AI processing tasks
  (window as any).requestIdleCallback = window.requestIdleCallback || ((cb: any) => {
    const start = Date.now();
    return setTimeout(() => {
      cb({
        didTimeout: false,
        timeRemaining: () => Math.max(0, 50 - (Date.now() - start)),
      });
    }, 1);
  });

  // Optimize Canvas and Streaming Render Performance via CSS Inject
  const style = document.createElement('style');
  style.innerHTML = 'canvas { will-change: transform; transform: translateZ(0); } .ai-stream-container { contain: content; }';
  document.head.appendChild(style);
}

// Initialize PostHog
posthog.init('YOUR_PROJECT_API_KEY', {
  api_host: 'https://eu.i.posthog.com',
  person_profiles: 'identified_only',
});

// Initialize Google Auth SDK for mobile and web platforms
GoogleAuth.initialize({
  clientId: 'YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com',
  scopes: ['profile', 'email'],
  grantOfflineAccess: true,
});

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