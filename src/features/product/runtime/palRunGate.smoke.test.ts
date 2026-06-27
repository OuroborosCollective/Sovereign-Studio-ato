import { describe, expect, it } from 'vitest';
import { decidePalRunGate } from './palRunGate';

describe('palRunGate smoke', () => {
  it('returns an answer action for chat questions', () => {
    const decision = decidePalRunGate({
      mission: 'Erklär mir kurz den Zustand',
      repoReady: false,
      repoFileCount: 0,
      context: 'chat',
    });

    expect(decision.allowed).toBe(true);
    expect(decision.action).toBe('answer');
  });
});
