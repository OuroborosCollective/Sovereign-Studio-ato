import React, { useEffect } from "react";
import { C } from "./builderConstants";
import type { WorkbenchStatusSlot } from "../runtime/builderWorkbenchStatus";

export interface WorkbenchSlotDrawerProps {
  slot: WorkbenchStatusSlot;
  onClose: () => void;
  onOpenDraftPr?: (url: string) => void;
}

export function WorkbenchSlotDrawer({
  slot,
  onClose,
  onOpenDraftPr,
}: WorkbenchSlotDrawerProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="workbench-slot-drawer-title"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 82,
        background: "rgba(14,17,22,0.82)",
        backdropFilter: "blur(6px)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-end",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 520,
          margin: "0 auto",
          maxHeight: "70vh",
          overflowY: "auto",
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderBottom: "none",
          borderRadius: "20px 20px 0 0",
          padding: "14px 16px calc(20px + env(safe-area-inset-bottom, 0px))",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <span
            id="workbench-slot-drawer-title"
            style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, color: C.text }}
          >
            {slot.label}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            title="Werkbank-Details schließen"
            className="focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:outline-none"
            style={{ background: "transparent", border: "none", color: C.textMuted, fontSize: 16, cursor: "pointer" }}
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>
        {slot.items.length === 0 ? (
          <div style={{ fontFamily: "monospace", fontSize: 11, color: C.textMuted, padding: "10px 0" }}>
            {slot.emptyLabel}
          </div>
        ) : (
          <ul
            role="list"
            aria-label={`${slot.label} Liste`}
            style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 6 }}
          >
            {slot.items.map((item, index) => (
              <li
                key={`${slot.id}-${index}`}
                style={{
                  fontFamily: "monospace",
                  fontSize: 11,
                  color: C.textSub,
                  padding: "6px 8px",
                  borderRadius: 8,
                  background: C.bg,
                  border: `1px solid ${C.border}`,
                  wordBreak: "break-word",
                }}
              >
                {item}
              </li>
            ))}
          </ul>
        )}
        {slot.id === "draftPr" && slot.items[0] && onOpenDraftPr && (
          <button
            type="button"
            onClick={() => onOpenDraftPr(slot.items[0])}
            aria-label={`Draft PR öffnen: ${slot.items[0]}`}
            title={`Draft PR öffnen: ${slot.items[0]}`}
            className="focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:outline-none"
            style={{
              marginTop: 12,
              width: "100%",
              padding: "10px 12px",
              borderRadius: 10,
              background: `${C.green}18`,
              border: `1px solid ${C.green}44`,
              color: C.green,
              fontFamily: "monospace",
              fontSize: 11,
              cursor: "pointer",
            }}
          >
            Draft PR öffnen
          </button>
        )}
      </div>
    </div>
  );
}
