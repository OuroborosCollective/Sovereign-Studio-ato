import React from "react";
import type { AgentStatus } from "../runtime/builderContainerHelpers";
import { C, STATUS_COLOR, STATUS_LABEL } from "./builderConstants";

export function Ampel({ status, compact = false }: { status: AgentStatus; compact?: boolean }) {
  const col = STATUS_COLOR[status];
  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: 5 }}
      title={STATUS_LABEL[status]}
    >
      {(["idle", "thinking", "editing"] as AgentStatus[]).map((s) => (
        <span
          key={s}
          style={{
            display: "inline-block",
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: status === s ? STATUS_COLOR[s] : `${STATUS_COLOR[s]}30`,
            boxShadow: status === s ? `0 0 6px ${STATUS_COLOR[s]}` : "none",
            transition: "all 0.3s",
          }}
        />
      ))}
      {!compact && (
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 10,
            color: col,
            marginLeft: 2,
          }}
        >
          {STATUS_LABEL[status]}
        </span>
      )}
    </div>
  );
}
