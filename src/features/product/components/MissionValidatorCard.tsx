import React from 'react';
import type { MissionValidationResult } from '../runtime/preflightMissionRuntime';
import { C } from './builderConstants';

export function MissionValidatorCard({
  result,
  onEdit,
  onStartAnyway,
}: {
  readonly result: MissionValidationResult;
  readonly onEdit: () => void;
  readonly onStartAnyway: () => void;
}) {
  return (
    <section
      role="alert"
      data-testid="mission-validator-card"
      style={{
        margin: '8px 12px',
        padding: 12,
        borderRadius: 12,
        border: `1px solid ${C.amber}55`,
        background: `${C.amber}0f`,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
        <div>
          <strong style={{ color: C.amber }}>Pre-flight Mission Validator</strong>
          <p style={{ margin: '4px 0 0', color: C.textSub, fontSize: 11 }}>
            Confidence {result.confidence}/100. Die Mission ist noch nicht ausreichend begrenzt.
          </p>
        </div>
        <span style={{ color: C.amber, fontFamily: 'monospace', fontWeight: 700 }}>
          {result.confidence}
        </span>
      </div>
      {result.questions.length > 0 && (
        <ol style={{ margin: '10px 0 0', paddingLeft: 18, color: C.text, fontSize: 11 }}>
          {result.questions.map((question) => <li key={question.id}>{question.question}</li>)}
        </ol>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}>
        <button type="button" onClick={onEdit} style={{ minHeight: 44, borderRadius: 10, border: `1px solid ${C.border}`, background: C.bg, color: C.text }}>
          Mission bearbeiten
        </button>
        <button type="button" onClick={onStartAnyway} style={{ minHeight: 44, borderRadius: 10, border: `1px solid ${C.amber}`, background: `${C.amber}18`, color: C.amber, fontWeight: 700 }}>
          Trotzdem starten
        </button>
      </div>
    </section>
  );
}
