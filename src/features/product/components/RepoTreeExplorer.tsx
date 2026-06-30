import React from 'react';

export interface RepoTreeExplorerProps {
  readonly onClose: () => void;
}

export function RepoTreeExplorer({ onClose }: RepoTreeExplorerProps) {
  return <button type="button" onClick={onClose}>Repo Inspector schließen</button>;
}

export default RepoTreeExplorer;
