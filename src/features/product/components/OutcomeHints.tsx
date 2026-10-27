import React from "react";
import type { ChatOutcomeHint } from "../runtime/builderContainerHelpers";
import { C } from "./builderConstants";

export function OutcomeHints({ hints }: { hints: ChatOutcomeHint[] }) {
  if (hints.length === 0) return null;
  return (
    <div style={{ padding: "0 12px 8px" }}>
      <div
        role="region"
        aria-label="Outcome Hints"
        style={{
          borderRadius: 10,
          border: `1px solid ${C.border}`,
          background: C.surface,
          padding: "10px 12px",
        }}
      >
        <ul
          role="list"
          aria-label="Outcome hints list"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 6,
            margin: 0,
            padding: 0,
            listStyle: "none",
          }}
        >
          {hints.map((h) => (
            <li
              key={`${h.kind}:${h.text}`}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 6,
                fontSize: 12,
                color: C.textSub,
              }}
            >
              <span
                aria-hidden="true"
                style={{ color: C.border, marginTop: 2, flexShrink: 0 }}
              >
                ›
              </span>
              {h.href ? (
                <a
                  href={h.href}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`${h.text} (opens in new tab)`}
                  title={`${h.text} (opens in new tab)`}
                  className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none rounded transition-opacity hover:opacity-80"
                  style={{
                    color: C.sky,
                    textDecoration: "underline",
                    textUnderlineOffset: 3,
                  }}
                >
                  {h.text}
                </a>
              ) : (
                <span>{h.text}</span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
