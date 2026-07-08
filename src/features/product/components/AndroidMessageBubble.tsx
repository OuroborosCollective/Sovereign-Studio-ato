import React, { useRef, useState, useCallback } from 'react';
import { ChatMarkdown } from './ChatMarkdown';
import { safeVibrate } from '../runtime/androidInteractionRuntime';
import { C } from './builderConstants';

export interface AndroidMessageBubbleProps {
  readonly role: 'user' | 'assistant';
  readonly text: string;
  readonly onQuote: (text: string) => void;
}

export function AndroidMessageBubble({ role, text, onQuote }: AndroidMessageBubbleProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
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

  const handleCopy = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard?.writeText(text);
      setCopied(true);
      safeVibrate(navigator, 5);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignored
    }
  }, [text]);

  return (
    <div
      data-testid="android-message-bubble"
      onContextMenu={(event) => { event.preventDefault(); openMenu(); }}
      onPointerDown={() => { clearTimer(); timer.current = setTimeout(openMenu, 520); }}
      onPointerUp={clearTimer}
      onPointerLeave={clearTimer}
      style={{ 
        margin: '8px 0', 
        padding: '12px 14px', 
        border: `1px solid ${C.border}`, 
        borderRadius: 16, 
        background: assistant ? C.asstBg : C.userBg,
        position: 'relative'
      }}
    >
      <div style={{ paddingRight: assistant ? 24 : 0 }}>
        {assistant ? <ChatMarkdown content={text} /> : text}
      </div>

      {assistant && (
        <button
          type="button"
          onClick={handleCopy}
          aria-label={copied ? 'Kopiert' : 'Nachricht kopieren'}
          style={{
            position: 'absolute',
            top: 6,
            right: 6,
            width: 32,
            height: 32,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: copied ? `${C.green}18` : 'transparent',
            border: 'none',
            borderRadius: 8,
            color: copied ? C.green : C.textMuted,
            fontSize: 14,
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
        >
          {copied ? '✓' : '📋'}
        </button>
      )}

      {menuOpen ? (
        <div 
          role="menu" 
          aria-label="Nachricht Aktionen"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            zIndex: 10,
            marginTop: 4,
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 12,
            padding: 4,
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            boxShadow: '0 4px 12px rgba(0,0,0,0.4)'
          }}
        >
          <button 
            type="button" 
            onClick={() => { navigator.clipboard?.writeText(text); setMenuOpen(false); }}
            style={{ padding: '8px 12px', background: 'transparent', border: 'none', color: C.text, textAlign: 'left', fontSize: 13, borderRadius: 8 }}
          >
            Kopieren
          </button>
          <button 
            type="button" 
            onClick={() => { onQuote(text); setMenuOpen(false); }}
            style={{ padding: '8px 12px', background: 'transparent', border: 'none', color: C.text, textAlign: 'left', fontSize: 13, borderRadius: 8 }}
          >
            Zitieren
          </button>
          <button 
            type="button" 
            onClick={() => setMenuOpen(false)}
            style={{ padding: '8px 12px', background: 'transparent', border: 'none', color: C.textMuted, textAlign: 'left', fontSize: 13, borderRadius: 8 }}
          >
            Abbrechen
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default AndroidMessageBubble;
