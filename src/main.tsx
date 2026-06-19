import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { installMobileOperatorCoach } from './mobile-operator-coach';
import { installMobileMoreMenu } from './mobile-more-menu';
import { installMobileSetupDrawer } from './mobile-setup-drawer';
import { installMobileWorkbenchConsole } from './mobile-workbench-console';
import './runtime-adapter';
import './index.css';

type IdleDeadlineLike = {
  didTimeout: boolean;
  timeRemaining: () => number;
};

type IdleCallbackLike = (deadline: IdleDeadlineLike) => void;

type GoogleAuthModule = {
  GoogleAuth?: {
    initialize?: (options: {
      clientId: string;
      scopes: string[];
      grantOfflineAccess: boolean;
    }) => void | Promise<void>;
  };
};

type MobileWindow = Window &
  typeof globalThis & {
    global?: Window & typeof globalThis;
    requestIdleCallback?: (callback: IdleCallbackLike) => number;
    cancelIdleCallback?: (handle: number) => void;
    __sovereignViewportRuntimeInstalled?: boolean;
    __sovereignMobileRuntimeInstalled?: boolean;
  };

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
] as const;

function bindViewportClasses(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const width = Math.max(1, window.innerWidth || 390);
  const height = Math.max(1, window.innerHeight || 844);
  const shortSide = Math.min(width, height);
  const longSide = Math.max(width, height);
  const root = document.documentElement;

  root.classList.remove(...VIEW_CLASSES);

  const deviceClass =
    shortSide >= 680
      ? 'device-tablet'
      : shortSide >= 540 && longSide >= 720
        ? 'device-foldable'
        : 'device-phone';

  root.classList.add(deviceClass);
  root.classList.add(width >= height ? 'is-landscape' : 'is-portrait');
  root.classList.add(height < 620 ? 'compact-height' : 'regular-height');
  root.classList.add(shortSide < 390 || (window.devicePixelRatio || 1) >= 3 ? 'compact-ui' : 'comfortable-ui');
}

function installIdleCallbackFallback(): void {
  if (typeof window === 'undefined') return;

  const mobileWindow = window as MobileWindow;
  mobileWindow.global = window;

  if (!mobileWindow.requestIdleCallback) {
    mobileWindow.requestIdleCallback = (callback: IdleCallbackLike): number => {
      const startedAt = Date.now();

      return window.setTimeout(() => {
        callback({
          didTimeout: false,
          timeRemaining: () => Math.max(0, 50 - (Date.now() - startedAt)),
        });
      }, 1);
    };
  }

  if (!mobileWindow.cancelIdleCallback) {
    mobileWindow.cancelIdleCallback = (handle: number): void => {
      window.clearTimeout(handle);
    };
  }
}

function installViewportRuntime(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const mobileWindow = window as MobileWindow;

  bindViewportClasses();

  if (!mobileWindow.__sovereignViewportRuntimeInstalled) {
    mobileWindow.__sovereignViewportRuntimeInstalled = true;

    window.addEventListener('resize', bindViewportClasses, { passive: true });
    window.addEventListener('orientationchange', bindViewportClasses, { passive: true });
  }

  if (!document.getElementById('sovereign-mobile-runtime-style')) {
    const style = document.createElement('style');
    style.id = 'sovereign-mobile-runtime-style';
    style.textContent = [
      'canvas { will-change: transform; transform: translateZ(0); }',
      '.ai-stream-container { contain: content; }',
      '@media (orientation: landscape) { #root > div.min-h-screen > div:nth-of-type(1) button { flex: 0 0 clamp(5.35rem, 12vw, 8rem); } }',
    ].join('\n');
    document.head.appendChild(style);
  }
}

function installMobileRuntimeModules(): void {
  if (typeof window === 'undefined') return;

  const mobileWindow = window as MobileWindow;
  if (mobileWindow.__sovereignMobileRuntimeInstalled) return;

  mobileWindow.__sovereignMobileRuntimeInstalled = true;

  installMobileOperatorCoach();
  installMobileMoreMenu();
  installMobileSetupDrawer();
  installMobileWorkbenchConsole();
}

function initPostHog(): void {
  const posthogKey = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
  const posthogHost = (import.meta.env.VITE_POSTHOG_HOST as string | undefined) ?? 'https://eu.i.posthog.com';

  if (!posthogKey) return;

  try {
    posthog.init(posthogKey, {
      api_host: posthogHost,
      person_profiles: 'identified_only',
    });
  } catch (error) {
    console.warn('PostHog init failed:', error);
  }
}

function initGoogleAuth(): void {
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
  if (!googleClientId) return;

  const googleAuthPackage = '@codetrix-studio/capacitor-google-auth';

  void import(/* @vite-ignore */ googleAuthPackage)
    .then((module: GoogleAuthModule) => {
      try {
        module.GoogleAuth?.initialize?.({
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

function bootApp(): void {
  const container = document.getElementById('root');

  if (!container) {
    console.warn('React root container #root not found.');
    return;
  }

  createRoot(container).render(
    <StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </StrictMode>,
  );
}

installIdleCallbackFallback();
installViewportRuntime();
installMobileRuntimeModules();
initPostHog();
initGoogleAuth();
bootApp();
