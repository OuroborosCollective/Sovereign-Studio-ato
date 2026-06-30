import React, { useRef, useState } from 'react';
import { ChatMarkdown } from './ChatMarkdown';
import { safeVibrate } from '../runtime/androidInteractionRuntime';

export interface AndroidMessageBubbleProps {
  readonly role: 'user' | 'assistant';
  readonly text: string;
  readonly onQuote: (text: string) => void;
}

export function AndroidMessageBubble({ role, text, onQuote }: AndroidMessageBubbleProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const assistant = role === 'assistant';

  const openMenu = () => {
    setMenuOpen(true);
    safeVibrate(navigator, 10);
  };

  const clearTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  return (
    <div
      data-testid="android-message-bubble"
      onContextMenu={(event) => { event.preventDefault(); openMenu(); }}
      onPointerDown={() => { clearTimer(); timer.current = setTimeout(openMenu, 520); }}
      onPointerUp={clearTimer}
      onPointerLeave={clearTimer}
      style={{ margin: '8px 0', padding: 10, border: '1px solid #232d3a', borderRadius: 12, background: assistant ? '#161c24' : '#1a2d45' }}
    >
      {assistant ? <ChatMarkdown content={text} /> : text}
      {menuOpen ? (
        <div role="menu" aria-label="Nachricht Aktionen">
          <button type="button" onClick={() => { navigator.clipboard?.writeText(text); setMenuOpen(false); }}>Kopieren</button>
          <button type="button" onClick={() => { onQuote(text); setMenuOpen(false); }}>Zitieren</button>
        </div>
      ) : null}
    </div>
  );
}

export default AndroidMessageBubble;
