import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PatternMemoryContainer } from './PatternMemoryContainer';
import { createSolutionPatternStore, type SolutionPatternStore } from '../runtime/solutionPatternMemory';

function storeWithPattern(): SolutionPatternStore {
  return {
    ...createSolutionPatternStore(1),
    updatedAt: 2,
    patterns: [{
      id: 'solve-one',
      status: 'active',
      problemSignature: 'p',
      contextFingerprint: 'c',
      fixFingerprint: 'f',
      category: 'docs',
      filePathHint: 'README.md',
      fileExtension: '.md',
      problemSummary: 'Missing useful guide.',
      beforeFingerprint: 'b',
      solutionSummary: 'Add a clear guide.',
      afterFingerprint: 'a',
      conditions: ['.md'],
      recommendedSteps: ['Add guide'],
      evidence: 'Manual verification.',
      intakeNode: 'learning-memory',
      processingNode: 'learning-memory',
      outputNodes: ['action-builder'],
      confidence: 'manual',
      tags: ['docs'],
      hits: 2,
      successfulUses: 0,
      rejectedUses: 0,
      createdAt: 1,
      updatedAt: 2,
    }],
  };
}

describe('PatternMemoryContainer', () => {
  it('renders empty memory and disables clear', () => {
    render(<PatternMemoryContainer store={createSolutionPatternStore(1)} onClear={vi.fn()} />);

    expect(screen.getByTestId('pattern-memory-container')).toBeDefined();
    expect(screen.getByText(/No local patterns learned yet/i)).toBeDefined();
    expect(screen.getByRole('button', { name: /Clear Pattern Memory/i })).toBeDisabled();
  });

  it('renders patterns and clears on demand', () => {
    const onClear = vi.fn();
    render(<PatternMemoryContainer store={storeWithPattern()} onClear={onClear} />);

    expect(screen.getByText(/Missing useful guide/i)).toBeDefined();
    expect(screen.getByText(/Add a clear guide/i)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /Clear Pattern Memory/i }));
    expect(onClear).toHaveBeenCalledOnce();
  });
});
