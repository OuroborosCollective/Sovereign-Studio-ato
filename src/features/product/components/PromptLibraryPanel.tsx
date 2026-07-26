import React, { useMemo, useState } from 'react';
import {
  availableCategories,
  categoryLabel,
  deleteCustomTemplate,
  filterTemplates,
  getAllTemplates,
  loadPromptLibraryState,
  saveCustomTemplate,
  type PromptCategory,
} from '../runtime/promptLibraryRuntime';
import { C } from './builderConstants';

export function PromptLibraryPanel({
  onSelectTemplate,
  onClose,
}: {
  readonly onSelectTemplate: (prompt: string) => void;
  readonly onClose: () => void;
}) {
  const storage = typeof window === 'undefined' ? null : window.localStorage;
  const [state, setState] = useState(() =>
    storage
      ? loadPromptLibraryState(storage)
      : { version: 1 as const, customTemplates: [], savedAt: 0 }
  );
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<PromptCategory | undefined>();
  const [add, setAdd] = useState(false);
  const [label, setLabel] = useState('');
  const [prompt, setPrompt] = useState('');
  const [newCategory, setNewCategory] = useState<PromptCategory>('custom');

  const templates = useMemo(
    () => filterTemplates(getAllTemplates(state), { query, category }),
    [state, query, category]
  );
  const categories = useMemo(() => availableCategories(getAllTemplates(state)), [state]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Prompt-Bibliothek"
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
            <strong style={{ flex: 1, color: C.text }}>📋 Prompt-Bibliothek</strong>
            <button
              type="button"
              onClick={onClose}
              aria-label="Bibliothek schließen"
              title="Bibliothek schließen"
              style={{
                minWidth: 44,
                minHeight: 44,
                background: 'transparent',
                border: 'none',
                color: C.text,
                cursor: 'pointer',
              }}
            >
              ×
            </button>
          </div>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Templates durchsuchen…"
            aria-label="Prompt-Templates suchen"
            style={{
              width: '100%',
              boxSizing: 'border-box',
              padding: 9,
              borderRadius: 8,
              border: `1px solid ${C.border}`,
              background: C.bg,
              color: C.text,
            }}
          />
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
            <button
              type="button"
              onClick={() => setCategory(undefined)}
              title="Alle Templates anzeigen"
              style={{
                color: !category ? C.sky : C.textMuted,
                background: 'transparent',
                border: `1px solid ${C.border}`,
                borderRadius: 8,
                padding: '5px 8px',
                cursor: 'pointer',
              }}
            >
              Alle
            </button>
            {categories.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setCategory(category === item ? undefined : item)}
                title={`Kategorie filtern: ${categoryLabel(item)}`}
                style={{
                  color: category === item ? C.sky : C.textMuted,
                  background: 'transparent',
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  padding: '5px 8px',
                  cursor: 'pointer',
                }}
              >
                {categoryLabel(item)}
              </button>
            ))}
          </div>
        </header>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {templates.map((item) => (
            <article key={item.id} style={{ padding: 12, borderBottom: `1px solid ${C.border}` }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <strong style={{ color: C.text, fontSize: 13 }}>{item.label}</strong>
                  <p
                    style={{
                      color: C.textMuted,
                      fontSize: 11,
                      whiteSpace: 'pre-wrap',
                      maxHeight: 72,
                      overflow: 'hidden',
                    }}
                  >
                    {item.prompt}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    onSelectTemplate(item.prompt);
                    onClose();
                  }}
                  title={`Template "${item.label}" für den Builder verwenden`}
                  style={{
                    alignSelf: 'center',
                    minHeight: 44,
                    padding: '7px 12px',
                    borderRadius: 9,
                    border: `1px solid ${C.sky}`,
                    background: `${C.sky}18`,
                    color: C.sky,
                    cursor: 'pointer',
                  }}
                >
                  Nutzen
                </button>
                {!item.isBuiltin && storage ? (
                  <button
                    type="button"
                    onClick={() => setState(deleteCustomTemplate(storage, state, item.id))}
                    aria-label="Template löschen"
                    title="Template löschen"
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: C.rose,
                      cursor: 'pointer',
                      fontSize: 18,
                      padding: '0 8px',
                    }}
                  >
                    ×
                  </button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
        <footer style={{ padding: 10, borderTop: `1px solid ${C.border}` }}>
          {!add ? (
            <button
              type="button"
              onClick={() => setAdd(true)}
              title="Eigenes Template erstellen"
              style={{
                width: '100%',
                minHeight: 44,
                borderRadius: 9,
                border: `1px dashed ${C.border}`,
                background: 'transparent',
                color: C.textMuted,
                cursor: 'pointer',
              }}
            >
              + Eigenes Template
            </button>
          ) : (
            <div style={{ display: 'grid', gap: 7 }}>
              <input
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="Bezeichnung"
                aria-label="Bezeichnung des eigenen Templates"
                style={{
                  padding: 8,
                  background: C.bg,
                  border: `1px solid ${C.border}`,
                  color: C.text,
                  borderRadius: 4,
                }}
              />
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="Prompt"
                aria-label="Inhalt des eigenen Templates"
                rows={4}
                style={{
                  padding: 8,
                  background: C.bg,
                  border: `1px solid ${C.border}`,
                  color: C.text,
                  borderRadius: 4,
                }}
              />
              <select
                value={newCategory}
                onChange={(event) => setNewCategory(event.target.value as PromptCategory)}
                aria-label="Kategorie des eigenen Templates"
                style={{
                  padding: 8,
                  background: C.bg,
                  color: C.text,
                  border: `1px solid ${C.border}`,
                  borderRadius: 4,
                }}
              >
                <option value="custom">Eigenes</option>
                <option value="analysis">Analyse</option>
                <option value="patch">Patch / PR</option>
                <option value="test">Tests</option>
                <option value="docs">Dokumentation</option>
                <option value="security">Security</option>
              </select>
              <div>
                <button
                  type="button"
                  disabled={!storage || !label.trim() || !prompt.trim()}
                  onClick={() => {
                    if (!storage) return;
                    const saved = saveCustomTemplate(storage, state, {
                      label,
                      prompt,
                      category: newCategory,
                    });
                    setState(saved.state);
                    setLabel('');
                    setPrompt('');
                    setAdd(false);
                  }}
                  title={
                    !label.trim() || !prompt.trim()
                      ? 'Bezeichnung und Prompt sind erforderlich'
                      : 'Eigenes Template speichern'
                  }
                  style={{
                    minHeight: 44,
                    padding: '7px 12px',
                    borderRadius: 9,
                    border: `1px solid ${C.green}`,
                    background: `${C.green}18`,
                    color: C.green,
                    cursor:
                      !storage || !label.trim() || !prompt.trim() ? 'not-allowed' : 'pointer',
                    opacity: !storage || !label.trim() || !prompt.trim() ? 0.6 : 1,
                  }}
                >
                  Speichern
                </button>
                <button
                  type="button"
                  onClick={() => setAdd(false)}
                  title="Erstellung abbrechen"
                  style={{
                    marginLeft: 8,
                    minHeight: 44,
                    background: 'transparent',
                    border: 'none',
                    color: C.textMuted,
                    cursor: 'pointer',
                  }}
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
