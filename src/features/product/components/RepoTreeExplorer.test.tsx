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

  it("calls close callback in dialog mode via button click and Escape key", () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <RepoTreeExplorer
        snapshot={snapshot()}
        onClose={onClose}
        onFileClick={() => {}}
      />,
    );

    fireEvent.click(screen.getByText("Schließen"));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);

    unmount();
    // After unmounting, Escape key listener should be removed
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("does not trigger onClose with Escape key when in split variant", () => {
    const onClose = vi.fn();
    render(
      <RepoTreeExplorer
        snapshot={snapshot()}
        variant="split"
        onClose={onClose}
        onFileClick={() => {}}
      />,
    );

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("has accessibility attributes and titles for folders and files", () => {
    render(
      <RepoTreeExplorer
        snapshot={snapshot()}
        onClose={() => {}}
        onFileClick={() => {}}
      />,
    );

    // Section should have aria-label
    expect(screen.getByRole("dialog", { name: "Repo Inspector" })).toBeTruthy();

    // Close button should have title, aria-label, and focus ring styling
    const closeBtn = screen.getByRole("button", { name: "Schließen" });
    expect(closeBtn).toHaveAttribute("title", "Schließen");
    expect(closeBtn).toHaveClass("focus-visible:ring-2");

    // Tree role and treeitems should be present
    expect(screen.getByRole("tree", { name: "Dateibaum" })).toBeTruthy();
    expect(screen.getAllByRole("treeitem").length).toBeGreaterThan(0);

    // Folder should have aria-label, title, and focus ring styling
    const folderBtn = screen.getByRole("button", { name: "Ordner schließen: src" });
    expect(folderBtn).toHaveAttribute("title", "Ordner schließen: src");
    expect(folderBtn).toHaveClass("focus-visible:ring-2");

    // File should have aria-label, title, and focus ring styling
    const fileBtn = screen.getByRole("button", { name: "Datei öffnen: README.md" });
    expect(fileBtn).toHaveAttribute("title", "Datei öffnen: README.md");
    expect(fileBtn).toHaveClass("focus-visible:ring-2");

    // Toggle folder and check label change
    fireEvent.click(folderBtn);
    const folderBtnOpened = screen.getByRole("button", { name: "Ordner öffnen: src" });
    expect(folderBtnOpened).toHaveAttribute("title", "Ordner öffnen: src");
  });

  it("renders split mode as navigation instead of a modal dialog", () => {
    render(
      <RepoTreeExplorer
        snapshot={snapshot()}
        variant="split"
        onFileClick={() => {}}
      />,
    );

    expect(screen.getByTestId("repo-split-inspector")).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Repo Baum Split Inspector" })).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Repo Inspector" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Schließen" })).toBeNull();
  });
});