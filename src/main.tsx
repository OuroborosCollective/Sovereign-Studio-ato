import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import posthog from 'posthog-js';
import App from './App.tsx';
import './index.css';

// Initialize PostHog
posthog.init('YOUR_PROJECT_API_KEY', {
  api_host: 'https://eu.i.posthog.com',
  person_profiles: 'identified_only',
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
