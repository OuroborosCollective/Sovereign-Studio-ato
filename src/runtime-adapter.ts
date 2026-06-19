/**
 * Runtime adapter for mobile fallback.
 *
 * NOTE:
 * The main mobile pane logic is handled by React state in useProductMagic.ts.
 * This file exists only as a defensive Android WebView / CSS fallback.
 *
 * No workflow auto-driver.
 * No idea factory.
 * No runtime state mutation.
 * No fake snapshot logic.
 */

const STYLE_ID = 'sovereign-mobile-pane-style';

function canUseDom(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof document !== 'undefined' &&
    typeof document.createElement === 'function'
  );
}

function installMobilePaneFallback(): void {
  if (!canUseDom()) return;

  const head = document.head || document.getElementsByTagName('head')[0];
  if (!head) return;

  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.setAttribute('data-runtime-adapter', 'mobile-pane-fallback');

  style.textContent = `
    /*
     * Mobile pane visibility is controlled by React.
     * This fallback only prevents broken initial layout in Android WebView
     * before React state has fully hydrated.
     */

    @media (min-width: 768px) {
      .mobile-pane-hidden {
        display: flex !important;
      }
    }

    @media (max-width: 767px) {
      .mobile-pane-hidden {
        display: none !important;
      }
    }
  `;

  head.appendChild(style);
}

function scheduleMobilePaneFallback(): void {
  if (!canUseDom()) return;

  const run = () => installMobilePaneFallback();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run, { once: true });
    return;
  }

  window.setTimeout(run, 0);
}

scheduleMobilePaneFallback();

export {};
