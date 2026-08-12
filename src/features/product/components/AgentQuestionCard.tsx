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
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [confirmFocused, setConfirmFocused] = useState(false);

  function handleConfirm() {
    if (selected && !disabled) {
      onAnswer(selected);
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (disabled) return;

    let nextIndex = index;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
      e.preventDefault();
      nextIndex = (index + 1) % options.length;
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
      e.preventDefault();
      nextIndex = (index - 1 + options.length) % options.length;
    } else {
      return;
    }

    const targetOption = options[nextIndex];
    if (targetOption) {
      setSelected(targetOption.id);
      setFocusedId(targetOption.id);
      setTimeout(() => {
        const btn = document.querySelector(`[data-option-id="${targetOption.id}"]`) as HTMLElement;
        if (btn) btn.focus();
      }, 0);
    }
  };

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
        {options.map((option, index) => {
          const isSelected = selected === option.id;
          const isFocused = focusedId === option.id;
          const tabIndex = isSelected || (selected === null && index === 0) ? 0 : -1;

          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={isSelected}
              tabIndex={tabIndex}
              data-option-id={option.id}
              disabled={disabled}
              onClick={() => setSelected(option.id)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              onFocus={() => setFocusedId(option.id)}
              onBlur={() => setFocusedId(null)}
              title={option.label}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '9px 12px',
                borderRadius: 8,
                background: isSelected ? `${C.accent}15` : 'transparent',
                border: `1px solid ${isSelected ? C.accent : C.border}`,
                outline: isFocused ? `2px solid ${C.accent}` : 'none',
                outlineOffset: isFocused ? '2px' : undefined,
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
        onFocus={() => setConfirmFocused(true)}
        onBlur={() => setConfirmFocused(false)}
        title={disabled ? 'Rückfrage bereits beantwortet' : !selected ? 'Bitte wählen Sie zuerst eine Option aus' : 'Ausgewählte Antwort an den Agenten senden'}
        style={{
          padding: '9px 16px',
          borderRadius: 8,
          background: selected && !disabled ? C.accent : C.border,
          border: 'none',
          outline: confirmFocused ? `2px solid ${C.accent}` : 'none',
          outlineOffset: confirmFocused ? '2px' : undefined,
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
