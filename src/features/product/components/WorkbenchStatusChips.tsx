import React from "react";
import { C } from "./builderConstants";
import {
  STATUS_FONT_SIZE_MIN,
  STATUS_TONE_ICON,
  STATUS_TONE_LABEL,
} from "../styles/statusTokens";
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
              minHeight: 44,
              padding: "8px 11px",
              borderRadius: 999,
              background: `${color}14`,
              border: `1px solid ${color}33`,
              color,
              fontFamily: "monospace",
              fontSize: STATUS_FONT_SIZE_MIN,
              cursor: "pointer",
              flexShrink: 0,
              whiteSpace: "nowrap",
            }}
          >
            <span
              role="img"
              aria-label={STATUS_TONE_LABEL[slot.tone]}
              title={STATUS_TONE_LABEL[slot.tone]}
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: STATUS_FONT_SIZE_MIN,
                lineHeight: 1,
              }}
            >
              {STATUS_TONE_ICON[slot.tone]}
            </span>
            <span style={{ color: C.textSub }}>{slot.label}</span>
            <span style={{ fontWeight: 700 }}>{slot.value}</span>
          </button>
        );
      })}
    </div>
  );
}
