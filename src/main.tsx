import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { installMobileOperatorCoach } from './mobile-operator-coach';
import { installMobileMoreMenu } from './mobile-more-menu';
import './runtime-adapter';
import './index.css';

const VIEW_CLASSES = [
  'device-phone',
  'device-foldable',
  'device-tablet',
  'is-portrait',
  'is-landscape',
  'compact-height',
  'regular-height',
  'compact-ui',
  'comfortable-ui',
];

function bindViewportClasses() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const width = Math.max(1, window.innerWidth || 390);
  const height = Math.max(1, window.innerHeight || 844);
  const shortSide = Math.min(width, height);
  const longSide = Math.max(width, height);
  const root = document.documentElement;
  root.classList.remove(...VIEW_CLASSES);
  const kind = shortSide >= 680 ? 'device-tablet' : shortSide >= 540 && longSide >= 720 ? 'device-foldable' : 'device-phone';
  root.classList.add(kind);
  root.classList.add(width >= height ? 'is-landscape' : 'is-portrait');
  root.classList.add(height < 620 ? 'compact-height' : 'regular-height');
  root.classList.add(shortSide < 390 || (window.devicePixelRatio || 1) >= 3 ? 'compact-ui' : 'comfortable-ui');
}

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

  bindViewportClasses();
  window.addEventListener('resize', bindViewportClasses, { passive: true });
  window.addEventListener('orientationchange', bindViewportClasses, { passive: true });

  const style = document.createElement('style');
  style.textContent = [
    'canvas { will-change: transform; transform: translateZ(0); }',
    '.ai-stream-container { contain: content; }',
    '@media (orientation: landscape) { #root > div.min-h-screen > div:nth-of-type(1) button { flex: 0 0 clamp(5.35rem, 12vw, 8rem); } }',
  ].join(' ');
  document.head.appendChild(style);

  installMobileOperatorCoach();
  installMobileMoreMenu();
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
