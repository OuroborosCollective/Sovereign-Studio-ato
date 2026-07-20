import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { LearnedPatternEntry } from '../runtime/patternMemoryRuntime';
import { PatternMemoryExplorer } from './PatternMemoryExplorer';

const ENTRY: LearnedPatternEntry = {
  id: 'pattern-verified-deploy',
  ownerScope: 'local-user',
  sourceTraceId: 'trace-verified-deploy',
  title: 'Verified deployment pattern',
  summary: 'Runs the verified deployment path with exact runtime evidence.',
  tags: ['deployment', 'evidence'],
  vectorRef: 'vector-pattern-verified-deploy',
  objectRef: null,
  verified: true,
  localExecutable: true,
  reuseCount: 2,
  lastUsedAt: null,
  createdAt: 1_700_000_000_000,
};

describe('PatternMemoryExplorer', () => {
  it('gives selectable pattern rows an explicit keyboard focus treatment', () => {
    const onSelectEntry = vi.fn();
    render(<PatternMemoryExplorer entries={[ENTRY]} onSelectEntry={onSelectEntry} />);

    const row = screen.getByRole('button', { name: /Verified deployment pattern/i });
    expect(row).toHaveClass('focus-visible:bg-slate-800');
    expect(row).toHaveClass('focus-visible:outline-none');
    expect(row).toHaveClass('focus-visible:ring-2');
    expect(row).toHaveClass('focus-visible:ring-sky-500');
    expect(row).toHaveClass('focus-visible:ring-offset-2');
    expect(row).toHaveClass('focus-visible:ring-offset-slate-950');

    fireEvent.click(row);
    expect(onSelectEntry).toHaveBeenCalledOnce();
    expect(onSelectEntry).toHaveBeenCalledWith(ENTRY.id);
  });

  it('keeps non-selectable pattern rows visually stable without a hover-only disabled override', () => {
    render(<PatternMemoryExplorer entries={[ENTRY]} />);

    const row = screen.getByRole('button', { name: /Verified deployment pattern/i });
    const hoverOnlyDisabledClass = ['disabled', 'hover', 'bg-slate-900'].join(':');
    expect(row).toBeDisabled();
    expect(row).toHaveClass('disabled:bg-slate-900');
    expect(row).not.toHaveClass(hoverOnlyDisabledClass);
  });
});
