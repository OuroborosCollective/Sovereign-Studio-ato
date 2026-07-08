import React from "react";
import { C } from "./builderConstants";
import type {
  WorkbenchStatusSlot,
  WorkbenchStatusTone,
} from "../runtime/builderWorkbenchStatus";
import type { ModuleCfg, ModuleId } from "../runtime/builderContainerTypes";
import type { RuntimeInspectorSignal } from "../runtime/runtimeInspectorPanelRuntime";

const WORKBENCH_STATUS_TONE_COLOR: Record<WorkbenchStatusTone, string> = {
  neutral: C.textMuted,
  positive: C.green,
  warning: C.amber,
  error: C.rose,
};

export interface WorkbenchSidePanelProps {
  slots: WorkbenchStatusSlot[];
  onOpenDraftPr?: (url: string) => void;
  modules: ModuleCfg[];
  signals: Partial<Record<ModuleId, number>>;
  showInspector: boolean;
  onToggleInspector: () => void;
}

export function WorkbenchSidePanel({
  slots,
  onOpenDraftPr,
  modules,
  signals,
  showInspector,
  onToggleInspector,
}: WorkbenchSidePanelProps) {
  return (
    <aside
      className="sovereign-side-panel"
      aria-label="Werkbank Übersicht"
      style={{
        flexDirection: "column",
        gap: 12,
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 16,
        padding: 14,
        boxSizing: "border-box",
      }}
    >
      <span style={{ fontFamily: "monospace", fontSize: 11, fontWeight: 700, color: C.textMuted, letterSpacing: 0.4 }}>
        WERKBANK
      </span>
      {slots.map((slot) => {
        const color = WORKBENCH_STATUS_TONE_COLOR[slot.tone];
        return (
          <div
            key={slot.id}
            style={{
              border: `1px solid ${C.border}`,
              borderRadius: 12,
              padding: 10,
              background: C.bg,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: color,
                  boxShadow: slot.tone !== "neutral" ? `0 0 4px ${color}` : "none",
                  display: "inline-block",
                }}
              />
              <span style={{ fontFamily: "monospace", fontSize: 11, fontWeight: 700, color }}>
                {slot.label}
              </span>
              <span style={{ fontFamily: "monospace", fontSize: 11, fontWeight: 700, color: C.textSub, marginLeft: "auto" }}>
                {slot.value}
              </span>
            </div>
            {slot.items.length === 0 ? (
              <div style={{ fontFamily: "monospace", fontSize: 10, color: C.textMuted }}>
                {slot.emptyLabel}
              </div>
            ) : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                {slot.items.slice(0, 6).map((item, index) => (
                  <li
                    key={`${slot.id}-side-${index}`}
                    style={{
                      fontFamily: "monospace",
                      fontSize: 10,
                      color: C.textSub,
                      padding: "4px 6px",
                      borderRadius: 6,
                      background: C.surface,
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
                style={{
                  marginTop: 8,
                  width: "100%",
                  padding: "8px 10px",
                  borderRadius: 8,
                  background: `${C.green}18`,
                  border: `1px solid ${C.green}44`,
                  color: C.green,
                  fontFamily: "monospace",
                  fontSize: 10,
                  cursor: "pointer",
                }}
              >
                Draft PR öffnen
              </button>
            )}
          </div>
        );
      })}
      <button
        type="button"
        onClick={onToggleInspector}
        aria-pressed={showInspector}
        style={{
          marginTop: 4,
          padding: "8px 10px",
          borderRadius: 8,
          background: showInspector ? `${C.accent}18` : "transparent",
          border: `1px solid ${showInspector ? C.accent : C.border}`,
          color: showInspector ? C.accent : C.textSub,
          fontFamily: "monospace",
          fontSize: 10,
          cursor: "pointer",
        }}
      >
        {showInspector ? "Inspector schließen" : "Inspector öffnen (intern)"}
      </button>
      {showInspector && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontFamily: "monospace", fontSize: 10, fontWeight: 700, color: C.textMuted }}>
            Module (intern)
          </span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {modules.map((m) => (
              <span
                key={m.id}
                title={m.short}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "4px 6px",
                  borderRadius: 6,
                  background: `${m.color}14`,
                  border: `1px solid ${m.color}33`,
                  color: m.color,
                  fontFamily: "monospace",
                  fontSize: 9,
                }}
              >
                <span>{m.icon}</span>
                <span>{m.short}</span>
                <span style={{ fontWeight: 700 }}>{signals[m.id] ?? 0}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}
