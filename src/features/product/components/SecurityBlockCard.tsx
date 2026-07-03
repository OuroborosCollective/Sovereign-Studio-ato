/**
 * SecurityBlockCard — shown inline in the chat feed when a secret / token
 * is detected in user input. Provides a clear action button to open the
 * secure GitHub access panel instead.
 *
 * Rule: Never instructs the user to enter a token in chat.
 */

import React from "react";
import { C } from "./builderConstants";

export interface SecurityBlockCardProps {
  readonly title: string;
  readonly text: string;
  readonly hint: string;
  readonly buttonLabel: string;
  readonly onOpenSecureAccess: () => void;
  readonly onDismiss: () => void;
}

export function SecurityBlockCard({
  title,
  text,
  hint,
  buttonLabel,
  onOpenSecureAccess,
  onDismiss,
}: SecurityBlockCardProps) {
  return (
    <div
      role="alert"
      aria-label={title}
      style={{
        margin: "0 16px",
        padding: "14px 16px",
        borderRadius: 10,
        background: "#1a1a2e",
        border: `1px solid ${C.rose}`,
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 16 }}>🔒</span>
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: C.rose,
            letterSpacing: 0.2,
          }}
        >
          {title}
        </span>
      </div>

      {/* Body */}
      <p style={{ margin: 0, fontSize: 13, color: C.text, lineHeight: 1.5 }}>
        {text}
      </p>

      {/* Hint */}
      {hint && (
        <p
          style={{
            margin: 0,
            fontSize: 11,
            color: C.textSub,
            fontStyle: "italic",
            lineHeight: 1.4,
          }}
        >
          {hint}
        </p>
      )}

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={onOpenSecureAccess}
          style={{
            padding: "8px 14px",
            borderRadius: 7,
            background: C.accent,
            color: C.bg,
            fontSize: 13,
            fontWeight: 600,
            border: "none",
            cursor: "pointer",
            flex: 1,
            minWidth: 160,
          }}
        >
          {buttonLabel}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          style={{
            padding: "8px 12px",
            borderRadius: 7,
            background: "transparent",
            color: C.textSub,
            fontSize: 12,
            border: `1px solid ${C.border}`,
            cursor: "pointer",
          }}
        >
          Schließen
        </button>
      </div>
    </div>
  );
}
