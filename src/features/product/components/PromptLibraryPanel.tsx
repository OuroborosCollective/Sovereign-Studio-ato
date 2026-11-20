import React, { useEffect, useMemo, useState } from 'react';
import { availableCategories, categoryLabel, deleteCustomTemplate, filterTemplates, getAllTemplates, loadPromptLibraryState, saveCustomTemplate, type PromptCategory } from '../runtime/promptLibraryRuntime';
import { C } from './builderConstants';

export function PromptLibraryPanel({ onSelectTemplate, onClose }: { readonly onSelectTemplate: (prompt: string) => void; readonly onClose: () => void }) {
  const storage = typeof window === 'undefined' ? null : window.localStorage;
  const [state, setState] = useState(() => storage ? loadPromptLibraryState(storage) : { version: 1 as const, customTemplates: [], savedAt: 0 });
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<PromptCategory | undefined>();
  const [add, setAdd] = useState(false);
  const [label, setLabel] = useState('');
  const [prompt, setPrompt] = useState('');
  const [newCategory, setNewCategory] = useState<PromptCategory>('custom');

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const templates = useMemo(() => filterTemplates(getAllTemplates(state), { query, category }), [state, query, category]);
  const categories = useMemo(() => availableCategories(getAllTemplates(state)), [state]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="prompt-library-title"
      data-testid="prompt-library-panel"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9998,
        background: 'rgba(0,0,0,.65)',
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'center',
      }}
    >
      <section
        onClick={(event) => event.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 700,
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: '18px 18px 0 0',
          overflow: 'hidden',
        }}
      >
        <header style={{ padding: 12, borderBottom: `1px solid ${C.border}` }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <strong id="prompt-library-title" style={{ flex: 1, color: C.text }}>📋 Prompt-Bibliothek</strong>
            <button
              type="button"
              onClick={onClose}
              aria-label="Prompt-Bibliothek schließen"
              title="Prompt-Bibliothek schließen"
              className="rounded focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none hover:opacity-80 transition-opacity"
              style={{ minWidth: 44, minHeight: 44, background: 'transparent', border: 'none', color: C.text }}
            >
              ×
            </button>
          </div>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Templates durchsuchen…"
            aria-label="Prompt-Templates suchen"
            title="Prompt-Templates suchen"
            className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
            style={{ width: '100%', boxSizing: 'border-box', padding: 9, borderRadius: 8, border: `1px solid ${C.border}`, background: C.bg, color: C.text }}
          />
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
            <button
              type="button"
              onClick={() => setCategory(undefined)}
              aria-pressed={!category}
              aria-label="Kategorie: Alle"
              title="Kategorie: Alle"
              className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none hover:opacity-80 transition-opacity"
              style={{ color: !category ? C.sky : C.textMuted, background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 8, padding: '5px 8px' }}
            >
              Alle
            </button>
            {categories.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setCategory(category === item ? undefined : item)}
                aria-pressed={category === item}
                aria-label={`Kategorie: ${categoryLabel(item)}`}
                title={`Kategorie: ${categoryLabel(item)}`}
                className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none hover:opacity-80 transition-opacity"
                style={{ color: category === item ? C.sky : C.textMuted, background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 8, padding: '5px 8px' }}
              >
                {categoryLabel(item)}
              </button>
            ))}
          </div>
        </header>
        <div style={{ flex: 1, overflow: 'auto' }}>
          <ul role="list" aria-label="Prompt-Templates" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {templates.map((item) => (
              <li key={item.id}>
                <article style={{ padding: 12, borderBottom: `1px solid ${C.border}` }}>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <div style={{ flex: 1 }}>
                      <strong style={{ color: C.text, fontSize: 13 }}>{item.label}</strong>
                      <p style={{ color: C.textMuted, fontSize: 11, whiteSpace: 'pre-wrap', maxHeight: 72, overflow: 'hidden' }}>{item.prompt}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        onSelectTemplate(item.prompt);
                        onClose();
                      }}
                      aria-label={`Template "${item.label}" nutzen`}
                      title={`Template "${item.label}" nutzen`}
                      className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none hover:opacity-80 transition-opacity"
                      style={{ alignSelf: 'center', minHeight: 44, padding: '7px 12px', borderRadius: 9, border: `1px solid ${C.sky}`, background: `${C.sky}18`, color: C.sky }}
                    >
                      Nutzen
                    </button>
                    {!item.isBuiltin && storage ? (
                      <button
                        type="button"
                        onClick={() => setState(deleteCustomTemplate(storage, state, item.id))}
                        aria-label={`Template "${item.label}" löschen`}
                        title={`Template "${item.label}" löschen`}
                        className="focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:outline-none hover:opacity-80 transition-opacity"
                        style={{ background: 'transparent', border: 'none', color: C.rose }}
                      >
                        ×
                      </button>
                    ) : null}
                  </div>
                </article>
              </li>
            ))}
          </ul>
        </div>
        <footer style={{ padding: 10, borderTop: `1px solid ${C.border}` }}>
          {!add ? (
            <button
              type="button"
              onClick={() => setAdd(true)}
              aria-label="Eigenes Template erstellen"
              title="Eigenes Template erstellen"
              className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none hover:opacity-80 transition-opacity"
              style={{ width: '100%', minHeight: 44, borderRadius: 9, border: `1px dashed ${C.border}`, background: 'transparent', color: C.textMuted }}
            >
              + Eigenes Template
            </button>
          ) : (
            <div style={{ display: 'grid', gap: 7 }}>
              <div style={{ display: 'grid', gap: 3 }}>
                <label htmlFor="prompt-template-label" style={{ fontSize: 11, color: C.textMuted }}>
                  Bezeichnung <span style={{ color: C.rose }}>*</span>
                </label>
                <input
                  id="prompt-template-label"
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  placeholder="Bezeichnung"
                  aria-label="Template Bezeichnung"
                  title="Template Bezeichnung"
                  className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
                  style={{ padding: 8, background: C.bg, border: `1px solid ${C.border}`, color: C.text, borderRadius: 6 }}
                />
              </div>
              <div style={{ display: 'grid', gap: 3 }}>
                <label htmlFor="prompt-template-text" style={{ fontSize: 11, color: C.textMuted }}>
                  Prompt <span style={{ color: C.rose }}>*</span>
                </label>
                <textarea
                  id="prompt-template-text"
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder="Prompt"
                  rows={4}
                  aria-label="Template Prompt Text"
                  title="Template Prompt Text"
                  className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
                  style={{ padding: 8, background: C.bg, border: `1px solid ${C.border}`, color: C.text, borderRadius: 6 }}
                />
              </div>
              <div style={{ display: 'grid', gap: 3 }}>
                <label htmlFor="prompt-template-category" style={{ fontSize: 11, color: C.textMuted }}>
                  Kategorie
                </label>
                <select
                  id="prompt-template-category"
                  value={newCategory}
                  onChange={(event) => setNewCategory(event.target.value as PromptCategory)}
                  aria-label="Template Kategorie"
                  title="Template Kategorie"
                  className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
                  style={{ padding: 8, background: C.bg, color: C.text, border: `1px solid ${C.border}`, borderRadius: 6 }}
                >
                  <option value="custom">Eigenes</option>
                  <option value="analysis">Analyse</option>
                  <option value="patch">Patch / PR</option>
                  <option value="test">Tests</option>
                  <option value="docs">Dokumentation</option>
                  <option value="security">Security</option>
                </select>
              </div>
              <div>
                <button
                  type="button"
                  disabled={!storage || !label.trim() || !prompt.trim()}
                  onClick={() => {
                    if (!storage) return;
                    const saved = saveCustomTemplate(storage, state, { label, prompt, category: newCategory });
                    setState(saved.state);
                    setLabel('');
                    setPrompt('');
                    setAdd(false);
                  }}
                  aria-label="Template speichern"
                  title="Template speichern"
                  className="focus-visible:ring-2 focus-visible:ring-green-500 focus-visible:outline-none hover:opacity-80 transition-opacity"
                  style={{ minHeight: 44, padding: '7px 12px', borderRadius: 9, border: `1px solid ${C.green}`, background: `${C.green}18`, color: C.green }}
                >
                  Speichern
                </button>
                <button
                  type="button"
                  onClick={() => setAdd(false)}
                  aria-label="Erstellung abbrechen"
                  title="Erstellung abbrechen"
                  className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none hover:opacity-80 transition-opacity"
                  style={{ marginLeft: 8, minHeight: 44, background: 'transparent', border: 'none', color: C.textMuted }}
                >
                  Abbrechen
                </button>
              </div>
            </div>
          )}
        </footer>
      </section>
    </div>
  );
}

export default PromptLibraryPanel;
