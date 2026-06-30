import React from 'react';
import type { SlashCommandDefinition } from '../runtime/slashCommandRuntime';

export interface SlashCommandMenuProps {
  readonly commands: readonly SlashCommandDefinition[];
  readonly selectedIndex: number;
  readonly onSelect: (command: SlashCommandDefinition) => void;
}

export function SlashCommandMenu({ commands, selectedIndex, onSelect }: SlashCommandMenuProps) {
  if (commands.length === 0) return null;
  return (
    <div role="listbox" aria-label="Sovereign Slash Commands" data-testid="slash-command-menu" style={{ border: '1px solid #232d3a', borderRadius: 12, background: '#161c24', padding: 6 }}>
      {commands.map((command, index) => (
        <button
          key={command.cmd}
          type="button"
          role="option"
          aria-selected={index === selectedIndex}
          onClick={() => onSelect(command)}
          style={{ width: '100%', textAlign: 'left', padding: '8px 10px', border: 0, borderRadius: 8, background: index === selectedIndex ? '#00d9b122' : 'transparent', color: '#cdd9e5', cursor: 'pointer' }}
        >
          <strong>{command.cmd}</strong>
          <span style={{ marginLeft: 8, color: '#768390' }}>{command.description}</span>
        </button>
      ))}
    </div>
  );
}

export default SlashCommandMenu;
