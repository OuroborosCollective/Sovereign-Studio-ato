import { describe, expect, it } from 'vitest';
import {
  canSubmitChatMessage,
  chatSidebarSummary,
  normalizeChatInput,
  normalizeChatMessages,
  normalizeSuggestions,
} from './chatSidebarRuntime';
import type { ChatMessage, Suggestion } from '../types';

describe('chatSidebarRuntime', () => {
  it('normalizes chat input before submit', () => {
    expect(normalizeChatInput('  hello   world  ')).toBe('hello world');
    expect(canSubmitChatMessage('   ')).toBe(false);
    expect(canSubmitChatMessage(' go ')).toBe(true);
  });

  it('filters invalid and empty messages safely', () => {
    const messages = normalizeChatMessages([
      { id: '', role: 'assistant', content: '  hello  ', timestamp: 1 },
      { id: 'bad', role: 'assistant', content: '   ', timestamp: 2 },
    ] as ChatMessage[]);

    expect(messages).toHaveLength(1);
    expect(messages[0].id).toBe('chat-0');
    expect(messages[0].content).toBe('hello');
  });

  it('normalizes suggestions for stable rendering', () => {
    const suggestions = normalizeSuggestions([
      { id: '', type: 'feature', title: '', description: '  test  ', priority: 'high' },
    ] as Suggestion[]);

    expect(suggestions).toHaveLength(1);
    expect(suggestions[0].id).toBe('suggestion-0');
    expect(suggestions[0].title).toBe('Untitled suggestion');
    expect(suggestions[0].description).toBe('test');
  });

  it('summarizes sidebar state', () => {
    const messages = normalizeChatMessages([{ id: 'm1', role: 'user', content: 'Hi', timestamp: 1 }]);
    const suggestions = normalizeSuggestions([{ id: 's1', type: 'feature', title: 'Add logs', description: 'desc', priority: 'low', accepted: true }]);

    expect(chatSidebarSummary(messages, suggestions)).toBe('1 message(s), 1 suggestion(s), 1 accepted.');
  });
});
