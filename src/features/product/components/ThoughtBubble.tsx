import React, { useEffect, useState } from "react";
import { C, WORKSTATE_TYPE_FRAME_MS, WORKSTATE_TYPE_STEP } from "./builderConstants";

function useTypedWorkStateText(text: string): string {
  const [visibleChars, setVisibleChars] = useState(text.length);

  useEffect(() => {
    setVisibleChars(Math.min(WORKSTATE_TYPE_STEP, text.length));
    if (!text.length) return undefined;

    const handle = window.setInterval(() => {
      setVisibleChars((current) => {
        if (current >= text.length) return current;
        return Math.min(text.length, current + WORKSTATE_TYPE_STEP);
      });
    }, WORKSTATE_TYPE_FRAME_MS);

    return () => window.clearInterval(handle);
  }, [text]);

  return text.slice(0, visibleChars);
}

export function ThoughtBubble({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const typedText = useTypedWorkStateText(text);
  const displayText =
    open || typedText.length <= 96 ? typedText : `${typedText.slice(0, 96)}…`;
  return (
    <button
      type="button"
      onClick={() => setOpen((v) => !v)}
      aria-live="polite"
      style={{
        width: "100%",
        background: "transparent",
        border: "none",
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        padding: "4px 16px",
        cursor: "pointer",
        textAlign: "left",
      }}
    >
      <span
        style={{
          fontFamily: "monospace",
          fontSize: 12,
          color: open ? C.sky : C.border,
          marginTop: 1,
          flexShrink: 0,
          transition: "color 0.2s",
        }}
      >
        ✦
      </span>
      <span
        style={{
          fontFamily: "monospace",
          fontSize: 10,
          fontStyle: "italic",
          lineHeight: 1.6,
          color: open ? C.textSub : C.textMuted,
          transition: "color 0.2s",
        }}
      >
        {displayText}
        <span
          aria-hidden="true"
          style={{
            color: C.sky,
            animation: "sdc-typing-caret 0.9s steps(2, start) infinite",
          }}
        >
          ▍
        </span>
      </span>
    </button>
  );
}
