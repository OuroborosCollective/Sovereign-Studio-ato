import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Download,
  Layout,
  LogOut,
  Plus,
  Save,
  Shield,
  Sparkles,
  Trash2,
  Upload,
  Zap,
} from 'lucide-react';

interface UserSession {
  id: string;
  email: string;
  name: string;
  imageUrl: string;
}

interface BoardCard {
  id: string;
  title: string;
  body: string;
  x: number;
  y: number;
  color: 'amber' | 'indigo' | 'emerald' | 'rose' | 'sky';
}

interface BoardState {
  title: string;
  blueprint: string;
  cards: BoardCard[];
  updatedAt: string;
}

const STORAGE_KEY = 'sovereign_canvas_tool_board_v1';
const COLORS: BoardCard['color'][] = ['amber', 'indigo', 'emerald', 'rose', 'sky'];

const makeId = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const defaultBoard = (): BoardState => ({
  title: 'Sovereign Canvas Tool',
  blueprint:
    'Temporärer Workflow: Repo-Ideen, Aufgaben, Cursor-Anweisungen und UI-Skizzen als bewegliche Karten ordnen.',
  updatedAt: new Date().toISOString(),
  cards: [
    {
      id: makeId(),
      title: 'Startpunkt',
      body: 'Schreibe links eine Anweisung und erzeuge daraus Karten für den Agenten-Workflow.',
      x: 42,
      y: 48,
      color: 'indigo',
    },
    {
      id: makeId(),
      title: 'Local-first',
      body: 'Das Board speichert lokal im Browser. Keine Tokens, keine Secrets, kein PAT-Feld.',
      x: 330,
      y: 110,
      color: 'emerald',
    },
    {
      id: makeId(),
      title: 'Export',
      body: 'JSON exportieren, später wieder importieren oder als Master-Prompt weiterverwenden.',
      x: 170,
      y: 300,
      color: 'amber',
    },
  ],
});

const cardStyle = (color: BoardCard['color']) => {
  const styles = {
    amber: 'bg-amber-100 border-amber-300 text-amber-950',
    indigo: 'bg-indigo-100 border-indigo-300 text-indigo-950',
    emerald: 'bg-emerald-100 border-emerald-300 text-emerald-950',
    rose: 'bg-rose-100 border-rose-300 text-rose-950',
    sky: 'bg-sky-100 border-sky-300 text-sky-950',
  };
  return styles[color];
};

const App: React.FC = () => {
  const boardRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null);

  const [user, setUser] = useState<UserSession | null>(null);
  const [board, setBoard] = useState<BoardState>(() => defaultBoard());
  const [activeCardId, setActiveCardId] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState('noch nicht');
  const [log, setLog] = useState<string[]>(['Canvas Tool bereit.']);

  const addLog = useCallback((line: string) => {
    setLog((current) => [`${new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} · ${line}`, ...current].slice(0, 8));
  }, []);

  useEffect(() => {
    const savedUser = localStorage.getItem('user_session');
    const savedBoard = localStorage.getItem(STORAGE_KEY);

    if (savedUser) {
      try {
        setUser(JSON.parse(savedUser) as UserSession);
      } catch {
        localStorage.removeItem('user_session');
      }
    }

    if (savedBoard) {
      try {
        setBoard(JSON.parse(savedBoard) as BoardState);
        setLastSaved('lokal geladen');
      } catch {
        localStorage.removeItem(STORAGE_KEY);
        addLog('Gespeichertes Board war beschädigt und wurde zurückgesetzt.');
      }
    }
  }, [addLog]);

  const login = () => {
    const session: UserSession = {
      id: makeId(),
      email: 'local@sovereign.studio',
      name: 'Sovereign User',
      imageUrl: '',
    };
    setUser(session);
    localStorage.setItem('user_session', JSON.stringify(session));
    addLog('Lokale Sitzung geöffnet.');
  };

  const logout = () => {
    localStorage.removeItem('user_session');
    setUser(null);
    addLog('Lokale Sitzung beendet.');
  };

  const updateBoard = (next: BoardState) => {
    setBoard({ ...next, updatedAt: new Date().toISOString() });
  };

  const addCard = useCallback((title = 'Neue Karte', body = board.blueprint) => {
    const index = board.cards.length;
    const nextCard: BoardCard = {
      id: makeId(),
      title,
      body: body.trim() || 'Leere Workflow-Karte.',
      x: 60 + (index % 4) * 74,
      y: 70 + (index % 5) * 52,
      color: COLORS[index % COLORS.length],
    };
    updateBoard({ ...board, cards: [...board.cards, nextCard] });
    setActiveCardId(nextCard.id);
    addLog('Karte erzeugt.');
  }, [addLog, board]);

  const removeCard = (id: string) => {
    updateBoard({ ...board, cards: board.cards.filter((card) => card.id !== id) });
    setActiveCardId(null);
    addLog('Karte gelöscht.');
  };

  const saveLocal = () => {
    const payload = { ...board, updatedAt: new Date().toISOString() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload, null, 2));
    setBoard(payload);
    setLastSaved(new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }));
    addLog('Board lokal gespeichert.');
  };

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(board, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `sovereign-canvas-board-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
    addLog('JSON exportiert.');
  };

  const importJson = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result)) as BoardState;
        if (!Array.isArray(parsed.cards)) throw new Error('Invalid board file');
        updateBoard({ ...parsed, updatedAt: new Date().toISOString() });
        localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed, null, 2));
        addLog(`Board importiert: ${file.name}`);
      } catch {
        addLog('Import fehlgeschlagen. Datei ist kein gültiges Board-JSON.');
      } finally {
        event.target.value = '';
      }
    };
    reader.readAsText(file);
  };

  const resetBoard = () => {
    const fresh = defaultBoard();
    updateBoard(fresh);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(fresh, null, 2));
    setActiveCardId(null);
    addLog('Board zurückgesetzt.');
  };

  const startDrag = (event: React.PointerEvent<HTMLDivElement>, card: BoardCard) => {
    const rect = event.currentTarget.getBoundingClientRect();
    dragRef.current = {
      id: card.id,
      dx: event.clientX - rect.left,
      dy: event.clientY - rect.top,
    };
    setActiveCardId(card.id);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const moveDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const boardElement = boardRef.current;
    if (!drag || !boardElement) return;

    const rect = boardElement.getBoundingClientRect();
    const x = Math.max(8, Math.min(event.clientX - rect.left - drag.dx, rect.width - 230));
    const y = Math.max(8, Math.min(event.clientY - rect.top - drag.dy, rect.height - 130));

    setBoard((current) => ({
      ...current,
      updatedAt: new Date().toISOString(),
      cards: current.cards.map((card) => (card.id === drag.id ? { ...card, x, y } : card)),
    }));
  };

  const stopDrag = () => {
    if (dragRef.current) addLog('Karte verschoben.');
    dragRef.current = null;
  };

  const activeCard = useMemo(
    () => board.cards.find((card) => card.id === activeCardId) ?? null,
    [activeCardId, board.cards]
  );

  const changeActiveCard = (patch: Partial<BoardCard>) => {
    if (!activeCard) return;
    updateBoard({
      ...board,
      cards: board.cards.map((card) => (card.id === activeCard.id ? { ...card, ...patch } : card)),
    });
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center p-6 text-center">
        <div className="max-w-md bg-white border border-stone-200 rounded-[2rem] p-8 shadow-xl">
          <div className="mx-auto mb-6 w-16 h-16 bg-indigo-600 rounded-3xl flex items-center justify-center text-white shadow-lg shadow-indigo-100">
            <Shield size={32} />
          </div>
          <h1 className="text-3xl font-black tracking-tight text-stone-900">Sovereign Canvas Tool</h1>
          <p className="mt-4 text-stone-500 leading-relaxed">
            Local-first Arbeitsfläche für temporäre Agent-Workflows, Architektur-Skizzen und No-Code-Anweisungen.
          </p>
          <button onClick={login} className="mt-8 w-full rounded-2xl bg-indigo-600 px-5 py-4 text-sm font-black uppercase tracking-wider text-white shadow-lg shadow-indigo-100 active:scale-95">
            Lokalen Workspace öffnen
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 flex flex-col">
      <header className="h-16 bg-white border-b border-stone-200 px-4 sm:px-6 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 bg-indigo-600 text-white rounded-2xl flex items-center justify-center shrink-0">
            <Shield size={20} />
          </div>
          <div className="min-w-0">
            <h1 className="font-black tracking-tight truncate">Sovereign Canvas Tool</h1>
            <p className="text-[10px] text-indigo-600 font-black uppercase tracking-[0.18em] truncate">Temporary workflow · local-first</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden sm:inline text-xs text-stone-500">{user.email}</span>
          <button onClick={logout} className="p-2 rounded-xl text-stone-400 hover:text-rose-600 hover:bg-rose-50" aria-label="Logout">
            <LogOut size={20} />
          </button>
        </div>
      </header>

      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)_320px] min-h-0">
        <aside className="bg-white border-b lg:border-b-0 lg:border-r border-stone-200 p-4 overflow-y-auto custom-scrollbar">
          <div className="flex items-center gap-2 mb-4">
            <Layout size={18} className="text-indigo-600" />
            <h2 className="text-sm font-black uppercase">Blueprint</h2>
          </div>

          <input
            value={board.title}
            onChange={(event) => updateBoard({ ...board, title: event.target.value })}
            className="w-full mb-3 rounded-2xl border border-stone-200 bg-stone-50 px-3 py-3 text-sm font-bold outline-none focus:border-indigo-500"
          />
          <textarea
            value={board.blueprint}
            onChange={(event) => updateBoard({ ...board, blueprint: event.target.value })}
            rows={8}
            className="w-full rounded-2xl border border-stone-200 bg-stone-50 p-3 text-xs leading-relaxed outline-none resize-none focus:border-indigo-500"
          />

          <div className="grid grid-cols-2 gap-2 mt-3">
            <button onClick={() => addCard('Agent Blueprint', board.blueprint)} className="col-span-2 rounded-2xl bg-stone-900 px-3 py-3 text-[11px] font-black uppercase text-white flex items-center justify-center gap-2 active:scale-95">
              <Sparkles size={14} /> Karte erzeugen
            </button>
            <button onClick={() => addCard()} className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-[10px] font-black uppercase text-indigo-800 flex items-center justify-center gap-1">
              <Plus size={13} /> Leer
            </button>
            <button onClick={saveLocal} className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-black uppercase text-emerald-800 flex items-center justify-center gap-1">
              <Save size={13} /> Speichern
            </button>
            <button onClick={exportJson} className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] font-black uppercase text-amber-800 flex items-center justify-center gap-1">
              <Download size={13} /> Export
            </button>
            <button onClick={() => fileRef.current?.click()} className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-[10px] font-black uppercase text-sky-800 flex items-center justify-center gap-1">
              <Upload size={13} /> Import
            </button>
          </div>

          <input ref={fileRef} type="file" accept="application/json" className="hidden" onChange={importJson} />

          <div className="mt-5 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-2xl bg-stone-50 border border-stone-200 p-3"><p className="text-[9px] font-black text-stone-400 uppercase">Karten</p><p className="font-black">{board.cards.length}</p></div>
            <div className="rounded-2xl bg-stone-50 border border-stone-200 p-3"><p className="text-[9px] font-black text-stone-400 uppercase">Save</p><p className="text-xs font-bold truncate">{lastSaved}</p></div>
            <div className="rounded-2xl bg-stone-50 border border-stone-200 p-3"><p className="text-[9px] font-black text-stone-400 uppercase">Mode</p><p className="text-xs font-bold">Live</p></div>
          </div>

          <button onClick={resetBoard} className="mt-4 w-full rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-[10px] font-black uppercase text-rose-700 flex items-center justify-center gap-1">
            <Trash2 size={13} /> Board zurücksetzen
          </button>
        </aside>

        <section className="min-h-[620px] lg:min-h-0 p-3 bg-stone-100/80">
          <div
            ref={boardRef}
            className="relative h-full min-h-[590px] overflow-hidden rounded-[2rem] border border-stone-200 bg-white shadow-inner touch-none"
            style={{ backgroundImage: 'linear-gradient(#e7e5e4 1px, transparent 1px), linear-gradient(90deg, #e7e5e4 1px, transparent 1px)', backgroundSize: '32px 32px' }}
            onPointerMove={moveDrag}
            onPointerUp={stopDrag}
            onPointerCancel={stopDrag}
          >
            <div className="absolute left-5 top-5 rounded-2xl bg-white/90 border border-stone-200 px-4 py-2 shadow-sm">
              <p className="text-xs font-black text-stone-800">{board.title}</p>
              <p className="text-[10px] text-stone-400">Karten ziehen · antippen zum Bearbeiten</p>
            </div>

            {board.cards.map((card) => (
              <div
                key={card.id}
                className={`absolute w-[220px] min-h-[126px] rounded-2xl border p-4 shadow-xl cursor-grab active:cursor-grabbing select-none ${cardStyle(card.color)} ${activeCardId === card.id ? 'ring-4 ring-indigo-400/30' : ''}`}
                style={{ left: card.x, top: card.y }}
                onPointerDown={(event) => startDrag(event, card)}
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-black text-sm leading-tight">{card.title}</h3>
                  <button onClick={(event) => { event.stopPropagation(); removeCard(card.id); }} className="text-current/40 hover:text-current">
                    <Trash2 size={14} />
                  </button>
                </div>
                <p className="mt-3 text-xs leading-relaxed whitespace-pre-wrap">{card.body}</p>
              </div>
            ))}
          </div>
        </section>

        <aside className="bg-stone-950 text-white border-t lg:border-t-0 lg:border-l border-stone-200 p-4 overflow-y-auto custom-scrollbar">
          <div className="flex items-center gap-2 mb-4">
            <Zap size={18} className="text-yellow-400" />
            <h2 className="text-sm font-black uppercase text-indigo-300">Inspector</h2>
          </div>

          {activeCard ? (
            <div className="space-y-3">
              <input value={activeCard.title} onChange={(event) => changeActiveCard({ title: event.target.value })} className="w-full rounded-xl bg-stone-900 border border-stone-700 px-3 py-2 text-sm font-bold outline-none focus:border-indigo-400" />
              <textarea value={activeCard.body} onChange={(event) => changeActiveCard({ body: event.target.value })} rows={8} className="w-full rounded-xl bg-stone-900 border border-stone-700 px-3 py-2 text-xs leading-relaxed outline-none resize-none focus:border-indigo-400" />
              <div className="grid grid-cols-5 gap-2">
                {COLORS.map((color) => <button key={color} onClick={() => changeActiveCard({ color })} className={`h-9 rounded-xl border ${cardStyle(color)} ${activeCard.color === color ? 'ring-2 ring-white' : ''}`} aria-label={color} />)}
              </div>
            </div>
          ) : (
            <p className="text-xs text-stone-400 leading-relaxed">Wähle eine Karte aus, um Titel, Text und Farbe zu bearbeiten.</p>
          )}

          <div className="mt-6 border-t border-stone-800 pt-4">
            <p className="text-[10px] font-black uppercase tracking-wider text-stone-500 mb-2">System Log</p>
            <div className="space-y-2">
              {log.map((line, index) => <div key={`${line}-${index}`} className="rounded-xl bg-stone-900 border border-stone-800 p-3 text-xs text-stone-300">{line}</div>)}
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
};

export default App;
