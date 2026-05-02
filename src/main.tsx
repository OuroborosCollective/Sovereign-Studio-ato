import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import { GoogleAuth } from '@codetrix-studio/capacitor-google-auth';
import App from './app/App.tsx';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';

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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);