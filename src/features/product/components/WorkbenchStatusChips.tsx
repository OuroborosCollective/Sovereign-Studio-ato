import React from "react";
import { C } from "./builderConstants";
import type {
  WorkbenchStatusSlot,
  WorkbenchStatusSlotId,
  WorkbenchStatusTone,
} from "../runtime/builderWorkbenchStatus";

const WORKBENCH_STATUS_TONE_COLOR: Record<WorkbenchStatusTone, string> = {
  neutral: C.textMuted,
  positive: C.green,
  warning: C.amber,
  error: C.rose,
};

export interface WorkbenchStatusChipsProps {
  slots: WorkbenchStatusSlot[];
  onSlotClick: (id: WorkbenchStatusSlotId) => void;
}

export function WorkbenchStatusChips({
  slots,
  onSlotClick,
}: WorkbenchStatusChipsProps) {
  return (
    <div
      role="tablist"
      aria-label="Werkbank Status"
      title="Werkbank Status"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 10px",
        borderTop: `1px solid ${C.border}`,
        overflowX: "auto",
      }}
    >
      {slots.map((slot) => {
        const color = WORKBENCH_STATUS_TONE_COLOR[slot.tone];
        return (
          <button
            key={slot.id}
            type="button"
            onClick={() => onSlotClick(slot.id)}
            aria-label={`${slot.label}: ${slot.value}`}
            title={`${slot.label}: ${slot.value}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              minHeight: 40,
              padding: "8px 11px",
              borderRadius: 999,
              background: `${color}14`,
              border: `1px solid ${color}33`,
              color,
              fontFamily: "monospace",
              fontSize: 10,
              cursor: "pointer",
              flexShrink: 0,
              whiteSpace: "nowrap",
            }}
          >
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
            <span style={{ color: C.textSub }}>{slot.label}</span>
            <span style={{ fontWeight: 700 }}>{slot.value}</span>
          </button>
        );
      })}
    </div>
  );
}
