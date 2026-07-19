/**
 * AgentQuestionCard - Displays agent questions as a card, not a text wall.
 *
 * User picks one option and confirms. The answer is forwarded to the runtime,
 * not stored in chat history as a free-text message.
 */

import React, { useState } from 'react';

const C = {
  surface:  '#161c24',
  border:   '#232d3a',
  accent:   '#00d9b1',
  text:     '#cdd9e5',
  textSub:  '#768390',
  amber:    '#fbbf24',
  sky:      '#22d3ee',
} as const;

export interface AgentQuestionOption {
  readonly id: string;
  readonly label: string;
}

export interface AgentQuestionCardProps {
  question: string;
  options: readonly AgentQuestionOption[];
  onAnswer: (optionId: string) => void;
  disabled?: boolean;
}

export const AgentQuestionCard: React.FC<AgentQuestionCardProps> = ({
  question,
  options,
  onAnswer,
  disabled = false,
}) => {
  const [selected, setSelected] = useState<string | null>(null);

  function handleConfirm() {
    if (selected && !disabled) {
      onAnswer(selected);
    }
  }

  return (
    <div
      role="group"
      aria-label="Agent Rückfrage"
      data-testid="agent-question-card"
      style={{
        margin: '8px 0',
        padding: '14px 16px',
        borderRadius: 12,
        background: C.surface,
        border: `1px solid ${C.amber}30`,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        maxWidth: 393,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <span style={{ fontSize: 14, lineHeight: 1, color: C.amber }}>?</span>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: C.amber, marginBottom: 4 }}>
            Sovereign braucht eine Entscheidung
          </div>
          <div style={{ fontSize: 13, color: C.text }}>
            {question}
          </div>
        </div>
      </div>

      <div
        role="radiogroup"
        aria-label="Optionen"
        style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
      >
        {options.map((option) => {
          const isSelected = selected === option.id;
          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={isSelected}
              disabled={disabled}
              onClick={() => setSelected(option.id)}
              title={option.label}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '9px 12px',
                borderRadius: 8,
                background: isSelected ? `${C.accent}15` : 'transparent',
                border: `1px solid ${isSelected ? C.accent : C.border}`,
                cursor: disabled ? 'not-allowed' : 'pointer',
                textAlign: 'left',
                opacity: disabled ? 0.5 : 1,
                transition: 'border-color 0.15s, background 0.15s',
              }}
            >
              <span
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: '50%',
                  border: `2px solid ${isSelected ? C.accent : C.textSub}`,
                  background: isSelected ? C.accent : 'transparent',
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {isSelected && (
                  <span
                    style={{
                      width: 5,
                      height: 5,
                      borderRadius: '50%',
                      background: C.surface,
                    }}
                  />
                )}
              </span>
              <span style={{ fontSize: 13, color: isSelected ? C.accent : C.text }}>
                {option.label}
              </span>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        disabled={!selected || disabled}
        onClick={handleConfirm}
        title={disabled ? 'Rückfrage bereits beantwortet' : !selected ? 'Bitte wählen Sie zuerst eine Option aus' : 'Ausgewählte Antwort an den Agenten senden'}
        style={{
          padding: '9px 16px',
          borderRadius: 8,
          background: selected && !disabled ? C.accent : C.border,
          border: 'none',
          color: selected && !disabled ? '#0e1116' : C.textSub,
          fontSize: 13,
          fontWeight: 600,
          cursor: selected && !disabled ? 'pointer' : 'not-allowed',
          alignSelf: 'flex-end',
          transition: 'background 0.15s',
        }}
      >
        An Agent senden
      </button>
    </div>
  );
};

export default AgentQuestionCard;
