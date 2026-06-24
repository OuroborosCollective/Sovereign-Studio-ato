import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { installGlobalRuntimeMonitor } from './global-runtime-monitor';
import { flushCanvasStateMirror, restoreCanvasStateMirror } from './store';
import './runtime-adapter';
import './index.css';
import './styles/arelogic-brand.css';
import './styles/sovereign-release-guide.css';
import './styles/sovereign-playtest-ux.css';

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

type ReleaseGuideCommandDetail = {
  type?: 'back' | 'confirm' | 'next';
  targetTab?: string | null;
};

type MobileWindow = Window &
  typeof globalThis & {
    global?: Window & typeof globalThis;
    requestIdleCallback?: (callback: IdleCallbackLike) => number;
    cancelIdleCallback?: (handle: number) => void;
    __sovereignViewportRuntimeInstalled?: boolean;
    __sovereignCodeWorkspacePersistenceInstalled?: boolean;
    __sovereignReleaseGuideCommandRuntimeInstalled?: boolean;
    __sovereignTabContentScrollRuntimeInstalled?: boolean;
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

const SAFE_TAB_ID = /^[a-z][a-z0-9-]*$/;

const TAB_CONTENT_SELECTORS: Record<string, string> = {
  repo: '[data-testid="repo-snapshot-container"]',
  builder: '[data-testid="builder-container"]',
  files: '[data-testid="generated-self-review"]',
  diff: '[data-testid="generated-file-diff-preview__internal"]',
  workflow: '[data-testid="workflow-container"]',
  telemetry: '[data-testid="telemetry-container"]',
  memory: '[data-testid="pattern-memory-container"]',
  monitor: '[data-testid="operator-monitor"]',
};

function normalize(value: string): string {
  return value.toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/\s+/g, ' ').trim();
}

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
      '@media (orientation: landscape) { .sovereign-tabbar button { flex: 0 0 clamp(5.35rem, 12vw, 8rem); } }',
    ].join('\n');
    document.head.appendChild(style);
  }
}

function isReleaseGuideButtonVisible(button: HTMLButtonElement): boolean {
  const style = window.getComputedStyle(button);
  return style.display !== 'none'
    && style.visibility !== 'hidden'
    && style.opacity !== '0'
    && button.getClientRects().length > 0;
}

function findReleaseGuideTargetButton(targetTab: string): HTMLButtonElement | null {
  const target = normalize(targetTab);
  const selectors = [
    `[data-testid="tabbar__${targetTab}"]`,
    `[data-role="sovereign-tab-${targetTab}"]`,
    `.sovereign-tab-${targetTab}`,
  ];

  for (const selector of selectors) {
    const button = document.querySelector<HTMLButtonElement>(selector);
    if (button) return button;
  }

  return Array.from(document.querySelectorAll<HTMLButtonElement>('button')).find((button) => {
    const text = normalize(button.textContent ?? '');
    const aria = normalize(button.getAttribute('aria-label') ?? '');
    const role = normalize(button.getAttribute('data-role') ?? '');
    const testId = normalize(button.getAttribute('data-testid') ?? '');

    return text === target
      || aria === `open ${target} tab`
      || role === `sovereign-tab-${target}`
      || testId === `tabbar__${target}`;
  }) ?? null;
}

function scrollTabContentIntoView(targetTab: string): void {
  const selector = TAB_CONTENT_SELECTORS[targetTab];
  if (!selector) return;

  window.setTimeout(() => {
    const target = document.querySelector<HTMLElement>(selector);
    if (!target) return;
    target.scrollIntoView({ block: 'start', inline: 'nearest', behavior: 'smooth' });
  }, 120);
}

function installTabContentScrollRuntime(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const mobileWindow = window as MobileWindow;
  if (mobileWindow.__sovereignTabContentScrollRuntimeInstalled) return;
  mobileWindow.__sovereignTabContentScrollRuntimeInstalled = true;

  document.addEventListener('click', (event) => {
    const button = (event.target instanceof Element ? event.target.closest<HTMLButtonElement>('button[data-testid^="tabbar__"]') : null);
    const testId = button?.getAttribute('data-testid') ?? '';
    const targetTab = testId.startsWith('tabbar__') ? testId.slice('tabbar__'.length) : '';
    if (targetTab && SAFE_TAB_ID.test(targetTab)) scrollTabContentIntoView(targetTab);
  });

  document.addEventListener('change', (event) => {
    const select = event.target instanceof HTMLSelectElement ? event.target : null;
    if (select?.getAttribute('data-testid') !== 'tabbar__more-select') return;
    const targetTab = select.value.trim();
    if (targetTab && SAFE_TAB_ID.test(targetTab)) scrollTabContentIntoView(targetTab);
  });
}

function activateReleaseGuideTarget(button: HTMLButtonElement, type?: ReleaseGuideCommandDetail['type']): void {
  button.classList.add('sovereign-next-step-highlight');
  window.setTimeout(() => button.classList.remove('sovereign-next-step-highlight'), 2800);

  if (isReleaseGuideButtonVisible(button)) {
    button.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }

  if (type !== 'confirm') {
    button.click();
    const testId = button.getAttribute('data-testid') ?? '';
    if (testId.startsWith('tabbar__')) scrollTabContentIntoView(testId.slice('tabbar__'.length));
  }
}

function installReleaseGuideCommandRuntime(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const mobileWindow = window as MobileWindow;
  if (mobileWindow.__sovereignReleaseGuideCommandRuntimeInstalled) return;
  mobileWindow.__sovereignReleaseGuideCommandRuntimeInstalled = true;

  window.addEventListener('sovereign:release-guide-command', (event: Event) => {
    const detail = (event as CustomEvent<ReleaseGuideCommandDetail>).detail;
    const targetTab = detail?.targetTab?.trim();
    if (!targetTab || !SAFE_TAB_ID.test(targetTab)) return;

    const button = findReleaseGuideTargetButton(targetTab);
    if (!button) return;

    activateReleaseGuideTarget(button, detail?.type);
  });
}

function installCodeWorkspacePersistenceRuntime(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const mobileWindow = window as MobileWindow;
  if (mobileWindow.__sovereignCodeWorkspacePersistenceInstalled) return;
  mobileWindow.__sovereignCodeWorkspacePersistenceInstalled = true;

  void restoreCanvasStateMirror({
    dispatch: true,
    clearInvalid: true,
  });

  const flushWorkspace = (): void => {
    void flushCanvasStateMirror();
  };

  window.addEventListener('pagehide', flushWorkspace, { passive: true });
  document.addEventListener(
    'visibilitychange',
    () => {
      if (document.visibilityState === 'hidden') flushWorkspace();
    },
    { passive: true },
  );
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
installReleaseGuideCommandRuntime();
installTabContentScrollRuntime();
installCodeWorkspacePersistenceRuntime();
installGlobalRuntimeMonitor();
initPostHog();
initGoogleAuth();
bootApp();
