import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { RepoTreeExplorer } from "./RepoTreeExplorer";
import type { DevChatRepoSnapshot } from "../runtime/devChatWorkerBridge";

function snapshot(
  overrides: Partial<DevChatRepoSnapshot> = {},
): DevChatRepoSnapshot {
  return {
    owner: "owner",
    repo: "repo",
    branch: "main",
    name: "repo",
    repoUrl: "local",
    fileCount: 4,
    files: [
      { path: "src/App.tsx", type: "blob" },
      {
        path: "src/features/product/containers/BuilderContainer.tsx",
        type: "blob",
      },
      {
        path: "src/features/product/runtime/repoTreeExplorerRuntime.ts",
        type: "blob",
      },
      { path: "README.md", type: "blob" },
    ],
    dirs: ["src"],
    truncated: false,
    ...overrides,
  };
}

describe("RepoTreeExplorer", () => {
  it("renders honest empty state without inventing repo data", () => {
    render(
      <RepoTreeExplorer
        snapshot={null}
        onClose={() => {}}
        onFileClick={() => {}}
      />,
    );

    expect(screen.getByText(/Repo-Snapshot fehlt/i)).toBeTruthy();
    expect(screen.getByText(/Kein Repo-Snapshot geladen/i)).toBeTruthy();
  });

  it("shows truncated snapshots clearly", () => {
    render(
      <RepoTreeExplorer
        snapshot={snapshot({ truncated: true })}
        onClose={() => {}}
        onFileClick={() => {}}
      />,
    );

    expect(screen.getAllByText(/truncated/i).length).toBeGreaterThanOrEqual(1);
  });

  it("opens and closes nested folders derived from the loaded snapshot", () => {
    render(
      <RepoTreeExplorer
        snapshot={snapshot()}
        onClose={() => {}}
        onFileClick={() => {}}
      />,
    );

    expect(screen.getByText("App.tsx")).toBeTruthy();
    fireEvent.click(screen.getByText("src"));
    expect(screen.queryByText("App.tsx")).toBeNull();
    fireEvent.click(screen.getByText("src"));
    expect(screen.getByText("App.tsx")).toBeTruthy();
  });

  it("calls file callback without auto-sending or fetching extra content", () => {
    const onFileClick = vi.fn();
    render(
      <RepoTreeExplorer
        snapshot={snapshot()}
        onClose={() => {}}
        onFileClick={onFileClick}
      />,
    );

    fireEvent.click(screen.getByText("App.tsx"));

    expect(onFileClick).toHaveBeenCalledWith("src/App.tsx");
  });

  it("renders a 500-item snapshot as a bounded inspector list", () => {
    const files = Array.from({ length: 500 }, (_, index) => ({
      path: `src/generated/file-${index}.ts`,
      type: "blob" as const,
      size: index,
    }));
    render(
      <RepoTreeExplorer
        snapshot={snapshot({ fileCount: 500, files })}
        onClose={() => {}}
        onFileClick={() => {}}
      />,
    );

    expect(screen.getByText(/500 Einträge/i)).toBeTruthy();
    expect(screen.getByText("generated")).toBeTruthy();
  });

  it("calls close callback", () => {
    const onClose = vi.fn();
    render(
      <RepoTreeExplorer
        snapshot={snapshot()}
        onClose={onClose}
        onFileClick={() => {}}
      />,
    );

    fireEvent.click(screen.getByText("Schließen"));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
