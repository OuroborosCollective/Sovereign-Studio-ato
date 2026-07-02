import type { AgentStatus } from "../runtime/builderContainerHelpers";

export const C = {
  bg: "#0e1116",
  surface: "#161c24",
  border: "#232d3a",
  borderHov: "#2e3d50",
  accent: "#00d9b1",
  accentDim: "#00d9b122",
  orange: "#f97316",
  text: "#cdd9e5",
  textSub: "#768390",
  textMuted: "#3d4f61",
  green: "#34d399",
  sky: "#22d3ee",
  amber: "#fbbf24",
  violet: "#a78bfa",
  rose: "#fb7185",
  userBg: "#1a2d45",
  asstBg: "#161c24",
} as const;

export const STATUS_COLOR: Record<AgentStatus, string> = {
  idle: C.green,
  thinking: C.sky,
  editing: C.amber,
  running: C.violet,
  error: C.rose,
};

export const STATUS_LABEL: Record<AgentStatus, string> = {
  idle: "bereit",
  thinking: "denkt…",
  editing: "editiert",
  running: "läuft",
  error: "fehler",
};

export const WORKSTATE_TYPE_FRAME_MS = 35;
export const WORKSTATE_TYPE_STEP = 2;
