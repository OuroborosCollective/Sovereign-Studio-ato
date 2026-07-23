import { beforeEach, describe, expect, it } from 'vitest';
import { availableCategories, BUILTIN_TEMPLATES, createEmptyState, deleteCustomTemplate, filterTemplates, getAllTemplates, loadPromptLibraryState, markTemplateUsed, saveCustomTemplate } from './promptLibraryRuntime';

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return Array.from(this.values.keys())[index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

describe('promptLibraryRuntime', () => {
  let storage: Storage;
  beforeEach(() => { storage = new MemoryStorage(); });
  it('ships eight built-in templates', () => expect(BUILTIN_TEMPLATES).toHaveLength(8));
  it('starts with no custom templates', () => expect(createEmptyState().customTemplates).toEqual([]));
  it('loads a safe empty state from corrupt storage', () => { storage.setItem('sovereign-studio.prompt-library.v1', '{'); expect(loadPromptLibraryState(storage).customTemplates).toEqual([]); });
  it('combines built-in and custom templates', () => { const saved = saveCustomTemplate(storage, createEmptyState(), { label: 'Mine', prompt: 'Do it', category: 'custom' }); expect(getAllTemplates(saved.state)).toHaveLength(9); });
  it('filters by category', () => expect(filterTemplates(BUILTIN_TEMPLATES, { category: 'test' })).toHaveLength(1));
  it('filters by search query', () => expect(filterTemplates(BUILTIN_TEMPLATES, { query: 'security' }).some((item) => item.category === 'security')).toBe(true));
  it('lists available categories', () => expect(availableCategories(BUILTIN_TEMPLATES)).toContain('analysis'));
  it('persists a custom template', () => { const saved = saveCustomTemplate(storage, createEmptyState(), { label: 'X', prompt: 'Y', category: 'custom' }); expect(loadPromptLibraryState(storage).customTemplates[0].id).toBe(saved.template.id); });
  it('deletes a custom template', () => { const saved = saveCustomTemplate(storage, createEmptyState(), { label: 'X', prompt: 'Y', category: 'custom' }); expect(deleteCustomTemplate(storage, saved.state, saved.template.id).customTemplates).toHaveLength(0); });
  it('marks a custom template as used', () => { const saved = saveCustomTemplate(storage, createEmptyState(), { label: 'X', prompt: 'Y', category: 'custom' }); const next = markTemplateUsed(storage, saved.state, saved.template.id); expect(next.customTemplates[0].useCount).toBe(1); expect(next.customTemplates[0].lastUsedAt).toBeTypeOf('number'); });
  it('does not mutate builtin counters in local state', () => { const state = createEmptyState(); expect(markTemplateUsed(storage, state, 'builtin-test')).toBe(state); });
});
