import React from "react";
import { C } from "./builderConstants";

export function FileBadge({
  path,
  file,
  onOpenFile,
}: {
  path?: string;
  file?: string;
  onOpenFile?: (path: string) => void;
}) {
  if (!file) return null;
  const fullPath = `${path ?? ""}${file}`;
  return (
    <button
      type="button"
      onClick={() => onOpenFile?.(fullPath)}
      disabled={!onOpenFile}
      aria-label={`Repo Datei öffnen: ${fullPath}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontFamily: "monospace",
        fontSize: 9,
        padding: "3px 8px",
        borderRadius: 6,
        background: "rgba(251,191,36,0.1)",
        border: "1px solid rgba(251,191,36,0.25)",
        color: C.amber,
        marginBottom: 4,
        maxWidth: "100%",
        overflow: "hidden",
        cursor: onOpenFile ? "pointer" : "default",
      }}
    >
      <span style={{ color: C.textMuted }}>{path}</span>
      <span>{file}</span>
    </button>
  );
}
