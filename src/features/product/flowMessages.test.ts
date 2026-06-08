import { describe, expect, it } from 'vitest';
import { flowMessage } from './flowMessages';

describe('flowMessages', () => {
  it('explains the work step for non technical users', () => {
    expect(flowMessage('work')).toContain('Chat');
    expect(flowMessage('work')).toContain('Live-Status');
  });
});
