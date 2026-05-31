import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle, X } from 'lucide-react';
import { keyStorage } from './keyStorage';

const VISIBLE_MS = 2500;

/**
 * Non-blocking toast that confirms whenever an API key (or any value) is
 * persisted via `keyStorage.set()`. Works in both the browser and the Android
 * WebView since it only relies on the in-app save event, not native UI.
 *
 * Rapid edits (typing into a key field fires a save per keystroke) are
 * debounced: the toast simply stays visible and resets its timer, so the user
 * sees a single confirmation ~2.5s after they stop typing.
 */
export default function KeySavedToast() {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const unsubscribe = keyStorage.onSaved(() => {
      setVisible(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setVisible(false), VISIBLE_MS);
    });
    return () => {
      unsubscribe();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const dismiss = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 text-white text-xs font-bold shadow-lg shadow-emerald-900/20 transition-opacity duration-200"
    >
      <CheckCircle size={15} />
      <span>Schlüssel gespeichert</span>
      <button
        onClick={dismiss}
        aria-label="Schließen"
        className="ml-1 rounded p-0.5 hover:bg-emerald-700/60 transition-colors"
      >
        <X size={13} />
      </button>
    </div>
  );
}
