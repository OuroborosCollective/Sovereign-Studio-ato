import React from 'react';
import type { SlashCommandDefinition } from '../runtime/slashCommandRuntime';

export interface SlashCommandMenuProps {
  readonly commands: readonly SlashCommandDefinition[];
  readonly selectedIndex: number;
  readonly onSelect: (command: SlashCommandDefinition) => void;
}

export function SlashCommandMenu({ commands, selectedIndex, onSelect }: SlashCommandMenuProps) {
  if (commands.length === 0) return null;
  const activeCommand = commands[selectedIndex];
  const activeId = activeCommand ? `slash-option-${activeCommand.cmd.replace(/[^a-zA-Z0-9_-]/g, '')}` : undefined;

  return (
    <div
      role="listbox"
      aria-label="Sovereign Slash Commands"
      aria-activedescendant={activeId}
      data-testid="slash-command-menu"
      style={{ border: '1px solid #232d3a', borderRadius: 12, background: '#161c24', padding: 6 }}
    >
      {commands.map((command, index) => {
        const optionId = `slash-option-${command.cmd.replace(/[^a-zA-Z0-9_-]/g, '')}`;
        const isSelected = index === selectedIndex;
        return (
          <button
            key={command.cmd}
            id={optionId}
            type="button"
            role="option"
            aria-selected={isSelected}
            title={`${command.cmd} – ${command.description}`}
            onClick={() => onSelect(command)}
            className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 transition-colors"
            style={{
              width: '100%',
              textAlign: 'left',
              padding: '8px 10px',
              border: 0,
              borderRadius: 8,
              background: isSelected ? '#00d9b122' : 'transparent',
              color: '#cdd9e5',
              cursor: 'pointer',
            }}
          >
            <strong>{command.cmd}</strong>
            <span style={{ marginLeft: 8, color: '#768390' }}>{command.description}</span>
          </button>
        );
      })}
    </div>
  );
}

export default SlashCommandMenu;
