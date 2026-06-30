import React from 'react';

export interface RuntimeInspectorPanelProps {
  readonly onClose: () => void;
}

export function RuntimeInspectorPanel({ onClose }: RuntimeInspectorPanelProps) {
  return <button type="button" onClick={onClose}>Inspector schließen</button>;
}

export default RuntimeInspectorPanel;
