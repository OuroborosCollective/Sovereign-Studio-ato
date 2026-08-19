/**
 * RuntimeEvidenceLogSheet accessibility tests (Issue #1567, findings E4/B3)
 * - Log message text at least 12px
 * - Log level conveyed via accessible icon (role="img" + aria-label), not color alone
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { RuntimeEvidenceLogSheet } from './RuntimeEvidenceLogSheet';
import type { SovereignRuntimeEvidenceLogEntry } from '../runtime/sovereignCompactShortcutExecutionRuntime';

function makeEntry(overrides: Partial<SovereignRuntimeEvidenceLogEntry>): SovereignRuntimeEvidenceLogEntry {
  return {
    id: 'e1',
    at: 1700000000000,
    source: 'action-stream',
    scope: 'agent',
    level: 'info',
    message: 'Runtime Ereignis',
    ...overrides,
  } as SovereignRuntimeEvidenceLogEntry;
}

describe('RuntimeEvidenceLogSheet accessibility', () => {
  it('renders log message text at least 12px', () => {
    const { getByText } = render(
      <RuntimeEvidenceLogSheet entries={[makeEntry({})]} onClose={() => {}} />,
    );
    const message = getByText('Runtime Ereignis');
    const logLine = message.closest('div');
    expect(parseFloat(logLine?.style.fontSize ?? '')).toBeGreaterThanOrEqual(12);
  });

  it('exposes the log level via an accessible icon label', () => {
    const { getByRole } = render(
      <RuntimeEvidenceLogSheet entries={[makeEntry({ level: 'error', id: 'e2' })]} onClose={() => {}} />,
    );
    expect(getByRole('img', { name: /error|fehler/i })).toBeTruthy();
  });

  it('labels warning levels accessibly as well', () => {
    const { getByRole } = render(
      <RuntimeEvidenceLogSheet entries={[makeEntry({ level: 'warning', id: 'e3' })]} onClose={() => {}} />,
    );
    expect(getByRole('img', { name: /warning|warnung/i })).toBeTruthy();
  });
});
