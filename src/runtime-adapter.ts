/**
 * Runtime adapter for mobile fallback.
 * 
 * NOTE: The main mobile pane logic is now handled by React state in useProductMagic.ts.
 * This file is kept for Android WebView compatibility and CSS fallback only.
 * Workflow auto-driver and idea factory have been moved to React components.
 */

function installMobilePaneFallback() {
  if (typeof document === 'undefined') return;
  if (document.getElementById('sovereign-mobile-pane-style')) return;

  // Only apply on smaller screens as fallback
  const style = document.createElement('style');
  style.id = 'sovereign-mobile-pane-style';
  style.textContent = `
    /* Mobile pane visibility is now controlled by React */
    /* This style is only for initial render fallback */
    @media (min-width: 768px) {
      .mobile-pane-hidden { display: flex !important; }
    }
    @media (max-width: 767px) {
      .mobile-pane-hidden { display: none !important; }
    }
  `;
  document.head.appendChild(style);
}

// Lightweight initialization - just for CSS fallback
if (typeof window !== 'undefined') {
  window.setTimeout(installMobilePaneFallback, 500);
}

export {};
