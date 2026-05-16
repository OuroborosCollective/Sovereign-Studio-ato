import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { store } from './store';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';

/**
 * Global Polyfills and Performance Optimizations
 * Target: WebView performance and stable canvas interactions.
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

const container = document.getElementById('root');

if (container) {
  const root = createRoot(container);
  root.render(
    <StrictMode>
      <ErrorBoundary>
        <Provider store={store}>
          <App />
        </Provider>
      </ErrorBoundary>
    </StrictMode>
  );
}
