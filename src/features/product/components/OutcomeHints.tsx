import React from "react";
import type { ChatOutcomeHint } from "../runtime/builderContainerHelpers";
import { safeHttpsUrl } from "../runtime/builderContainerHelpers";
import { C } from "./builderConstants";

export function OutcomeHints({ hints }: { hints: ChatOutcomeHint[] }) {
  if (hints.length === 0) return null;
  return (
    <div style={{ padding: "0 12px 8px" }}>
      <div
        style={{
          borderRadius: 10,
          border: `1px solid ${C.border}`,
          background: C.surface,
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 6,
        }}
      >
        {hints.map((h) => {
          const safeHref = h.href ? safeHttpsUrl(h.href) : undefined;
          return (
            <div
              key={`${h.kind}:${h.text}`}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 6,
                fontSize: 12,
                color: C.textSub,
              }}
            >
              <span style={{ color: C.border, marginTop: 2, flexShrink: 0 }}>
                ›
              </span>
              {safeHref ? (
                <a
                  href={safeHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    color: C.sky,
                    textDecoration: "underline",
                    textUnderlineOffset: 3,
                  }}
                >
                  {h.text}
                </a>
              ) : (
                h.text
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
