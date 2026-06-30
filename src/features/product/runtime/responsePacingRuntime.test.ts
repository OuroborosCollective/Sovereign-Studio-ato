import { describe, expect, it } from 'vitest';
import { createAssistantResponsePacingState } from './assistantResponsePacingRuntime';

describe('response pacing runtime', () => {
  it('keeps short messages immediate', () => {
    const state = createAssistantResponsePacingState('short text', 1);

    expect(state.shouldPace).toBe(false);
    expect(state.visibleText).toBe('short text');
    expect(state.complete).toBe(true);
  });
});
