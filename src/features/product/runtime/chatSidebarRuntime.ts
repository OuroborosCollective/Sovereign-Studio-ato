import type { ChatMessage, Suggestion, SuggestionType } from '../types';
import { maskSecrets } from '../../../shared/utils/crypto';

export const CHAT_SIDEBAR_MAX_INPUT = 2000;
export const CHAT_SIDEBAR_MAX_MESSAGE = 4000;
export const CHAT_SIDEBAR_MAX_ITEMS = 200;

const KNOWN_ROLES = new Set(['user', 'assistant', 'system']);
const KNOWN_SUGGESTION_TYPES = new Set(['feature', 'error', 'improvement']);
const KNOWN_PRIORITIES = new Set(['high', 'medium', 'low']);

function trimText(value: unknown, max = CHAT_SIDEBAR_MAX_MESSAGE): string {
  return String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, max);
}

function safeId(value: unknown, fallback: string): string {
  const normalized = trimText(value, 80).replace(/[^a-zA-Z0-9._:-]+/g, '-').replace(/^-|-$/g, '');
  return normalized || fallback;
}

function safeTimestamp(value: unknown, fallback: number): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 ? numeric : fallback;
}

export function normalizeChatInput(value: string): string {
  return maskSecrets(trimText(value, CHAT_SIDEBAR_MAX_INPUT));
}

export function canSubmitChatMessage(value: string): boolean {
  return normalizeChatInput(value).length > 0;
}

export function normalizeChatMessages(messages: readonly ChatMessage[] | null | undefined): ChatMessage[] {
  if (!Array.isArray(messages)) return [];
  return messages
    .slice(-CHAT_SIDEBAR_MAX_ITEMS)
    .map((message, index): ChatMessage => {
      const role = KNOWN_ROLES.has(message.role) ? message.role : 'assistant';
      return {
        id: safeId(message.id, `chat-${index}`),
        role,
        content: maskSecrets(trimText(message.content)),
        timestamp: safeTimestamp(message.timestamp, index),
      };
    })
    .filter((message) => message.content.length > 0);
}

export function normalizeSuggestions(suggestions: readonly Suggestion[] | null | undefined): Suggestion[] {
  if (!Array.isArray(suggestions)) return [];
  return suggestions
    .slice(0, CHAT_SIDEBAR_MAX_ITEMS)
    .map((suggestion, index): Suggestion => {
      const type = KNOWN_SUGGESTION_TYPES.has(suggestion.type) ? suggestion.type : 'feature';
      const priority = KNOWN_PRIORITIES.has(suggestion.priority) ? suggestion.priority : 'low';
      return {
        id: safeId(suggestion.id, `suggestion-${index}`),
        type: type as SuggestionType,
        title: maskSecrets(trimText(suggestion.title, 240) || 'Untitled suggestion'),
        description: maskSecrets(trimText(suggestion.description, 1000)),
        priority: priority as Suggestion['priority'],
        accepted: Boolean(suggestion.accepted),
      };
    });
}

export function describeSuggestionAction(suggestion: Suggestion): string {
  return suggestion.accepted ? `Accepted suggestion: ${suggestion.title}` : `Accept suggestion: ${suggestion.title}`;
}

export function chatSidebarSummary(messages: readonly ChatMessage[], suggestions: readonly Suggestion[]): string {
  const accepted = suggestions.filter((suggestion) => suggestion.accepted).length;
  return `${messages.length} message(s), ${suggestions.length} suggestion(s), ${accepted} accepted.`;
}
