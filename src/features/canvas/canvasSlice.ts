import { createSlice, type PayloadAction } from '@reduxjs/toolkit';

/**
 * Erweitertes Typ-System für Fabric.js Objekte inklusive KI-spezifischer Entitäten.
 */
export type FabricObjectType =
  | 'rect'
  | 'circle'
  | 'path'
  | 'image'
  | 'i-text'
  | 'textbox'
  | 'group'
  | 'ai-text'
  | 'activeSelection';

/**
 * Konsolidiertes Interface für Canvas-Objekte innerhalb der Sovereign Studio Architektur.
 * Dient als Single Source of Truth für UI-Synchronisation und KI-Manipulation.
 */
export interface CanvasObject {
  id: string;
  type: FabricObjectType | string;
  x?: number;
  y?: number;
  left: number;
  top: number;
  width: number;
  height: number;
  scaleX: number;
  scaleY: number;
  angle: number;
  flipX: boolean;
  flipY: boolean;
  opacity: number;
  visible: boolean;
  fill?: string | unknown;
  stroke?: string;
  strokeWidth?: number;
  originX?: 'left' | 'center' | 'right' | string;
  originY?: 'top' | 'center' | 'bottom' | string;
  zIndex: number;
  data?: unknown;

  // Text & KI-Text Eigenschaften
  text?: string;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: string | number;
  textAlign?: 'left' | 'center' | 'right' | 'justify';
  lineHeight?: number;
  charSpacing?: number;

  // Bild Eigenschaften
  src?: string;
  crossOrigin?: string;

  // Vektor Eigenschaften
  path?: unknown[];

  // Metadaten & Status für KI-Vorgänge
  locked?: boolean;
  aiGenerated?: boolean;
  promptSource?: string;
  metadata?: Record<string, unknown>;

  [key: string]: unknown;
}

export interface CanvasState {
  objects: CanvasObject[];
  selectedIds: string[];
  viewbox: {
    zoom: number;
    panX: number;
    panY: number;
  };
  isDragging: boolean;
}

export const CANVAS_STATE_SCHEMA_VERSION = 1 as const;

const initialState: CanvasState = {
  objects: [],
  selectedIds: [],
  viewbox: {
    zoom: 1,
    panX: 0,
    panY: 0,
  },
  isDragging: false,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringOrFallback(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function finiteNumberOrFallback(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function booleanOrFallback(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function normalizeCanvasObject(value: unknown, index: number): CanvasObject | null {
  if (!isRecord(value)) return null;

  const id = stringOrFallback(value.id, `restored-canvas-object-${index}`);
  const type = stringOrFallback(value.type, 'rect');
  const zIndex = finiteNumberOrFallback(value.zIndex, index);

  return {
    ...value,
    id,
    type,
    left: finiteNumberOrFallback(value.left, finiteNumberOrFallback(value.x, 0)),
    top: finiteNumberOrFallback(value.top, finiteNumberOrFallback(value.y, 0)),
    width: finiteNumberOrFallback(value.width, 0),
    height: finiteNumberOrFallback(value.height, 0),
    scaleX: finiteNumberOrFallback(value.scaleX, 1),
    scaleY: finiteNumberOrFallback(value.scaleY, 1),
    angle: finiteNumberOrFallback(value.angle, 0),
    flipX: booleanOrFallback(value.flipX, false),
    flipY: booleanOrFallback(value.flipY, false),
    opacity: finiteNumberOrFallback(value.opacity, 1),
    visible: booleanOrFallback(value.visible, true),
    zIndex,
  };
}

function normalizeSelectedIds(value: unknown, validObjectIds: Set<string>): string[] {
  if (!Array.isArray(value)) return [];

  const selectedIds: string[] = [];
  const seen = new Set<string>();

  for (const item of value) {
    if (typeof item !== 'string') continue;
    if (!validObjectIds.has(item)) continue;
    if (seen.has(item)) continue;

    seen.add(item);
    selectedIds.push(item);
  }

  return selectedIds;
}

function normalizeViewbox(value: unknown): CanvasState['viewbox'] {
  if (!isRecord(value)) return { ...initialState.viewbox };

  return {
    zoom: finiteNumberOrFallback(value.zoom, initialState.viewbox.zoom),
    panX: finiteNumberOrFallback(value.panX, initialState.viewbox.panX),
    panY: finiteNumberOrFallback(value.panY, initialState.viewbox.panY),
  };
}

function sortObjectsByZIndex(objects: CanvasObject[]): CanvasObject[] {
  return [...objects].sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
}

export function normalizeCanvasStateInput(value: unknown): CanvasState | null {
  if (!isRecord(value)) return null;

  const rawObjects = Array.isArray(value.objects) ? value.objects : [];
  const objects = sortObjectsByZIndex(
    rawObjects
      .map((object, index) => normalizeCanvasObject(object, index))
      .filter((object): object is CanvasObject => Boolean(object)),
  );

  const objectIds = new Set(objects.map((object) => object.id));

  return {
    objects,
    selectedIds: normalizeSelectedIds(value.selectedIds, objectIds),
    viewbox: normalizeViewbox(value.viewbox),
    isDragging: booleanOrFallback(value.isDragging, false),
  };
}

export function getInitialCanvasState(): CanvasState {
  return {
    objects: [],
    selectedIds: [],
    viewbox: {
      ...initialState.viewbox,
    },
    isDragging: initialState.isDragging,
  };
}

export const canvasSlice = createSlice({
  name: 'canvas',
  initialState,
  reducers: {
    /**
     * Fügt ein neues Objekt hinzu und bewahrt die zIndex-Integrität.
     */
    addObject: (state, action: PayloadAction<CanvasObject>) => {
      const exists = state.objects.some((obj) => obj.id === action.payload.id);
      if (!exists) {
        state.objects.push(action.payload);
        state.objects.sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
      }
    },

    /**
     * Batch-Insert für Vektor-Gruppen oder KI-generierte Szenen.
     */
    addVectors: (state, action: PayloadAction<CanvasObject[]>) => {
      const existingIds = new Set<string>();
      for (let index = 0; index < state.objects.length; index += 1) {
        existingIds.add(state.objects[index].id);
      }

      action.payload.forEach((newObj) => {
        if (!existingIds.has(newObj.id)) {
          state.objects.push(newObj);
          existingIds.add(newObj.id);
        }
      });

      state.objects.sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
    },

    /**
     * Partielle Aktualisierung eines Objekts. Löst Sortierung bei zIndex-Änderung aus.
     */
    updateObject: (state, action: PayloadAction<Partial<CanvasObject> & { id: string }>) => {
      const index = state.objects.findIndex((obj) => obj.id === action.payload.id);
      if (index !== -1) {
        state.objects[index] = { ...state.objects[index], ...action.payload };

        if (action.payload.zIndex !== undefined) {
          state.objects.sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
        }
      }
    },

    removeObject: (state, action: PayloadAction<string>) => {
      const idToRemove = action.payload;
      const newObjects: CanvasObject[] = [];

      for (const obj of state.objects) {
        if (obj.id !== idToRemove) {
          newObjects.push(obj);
        }
      }

      state.objects = newObjects;

      const newSelectedIds: string[] = [];
      for (const id of state.selectedIds) {
        if (id !== idToRemove) {
          newSelectedIds.push(id);
        }
      }

      state.selectedIds = newSelectedIds;
    },

    removeObjects: (state, action: PayloadAction<string[]>) => {
      const idsToRemove = new Set(action.payload);
      const newObjects: CanvasObject[] = [];

      for (const obj of state.objects) {
        if (!idsToRemove.has(obj.id)) {
          newObjects.push(obj);
        }
      }

      state.objects = newObjects;

      const newSelectedIds: string[] = [];
      for (const id of state.selectedIds) {
        if (!idsToRemove.has(id)) {
          newSelectedIds.push(id);
        }
      }

      state.selectedIds = newSelectedIds;
    },

    selectObjects: (state, action: PayloadAction<string[]>) => {
      const validIds = new Set(state.objects.map((object) => object.id));
      state.selectedIds = normalizeSelectedIds(action.payload, validIds);
    },

    setZIndex: (state, action: PayloadAction<{ id: string; zIndex: number }>) => {
      const obj = state.objects.find((o) => o.id === action.payload.id);
      if (obj) {
        obj.zIndex = action.payload.zIndex;
        state.objects.sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
      }
    },

    /**
     * Verschiebt ein Layer relativ in der Hierarchie und normalisiert zIndex.
     */
    moveLayer: (state, action: PayloadAction<{ id: string; delta: number }>) => {
      const index = state.objects.findIndex((o) => o.id === action.payload.id);
      if (index === -1) return;

      const newIndex = Math.max(
        0,
        Math.min(state.objects.length - 1, index + action.payload.delta),
      );
      const [removed] = state.objects.splice(index, 1);
      state.objects.splice(newIndex, 0, removed);

      // Normalisierung der Indizes für konsistente Rendering-Pipeline
      state.objects.forEach((obj, itemIndex) => {
        obj.zIndex = itemIndex;
      });
    },

    setViewbox: (state, action: PayloadAction<Partial<CanvasState['viewbox']>>) => {
      state.viewbox = {
        zoom: finiteNumberOrFallback(action.payload.zoom, state.viewbox.zoom),
        panX: finiteNumberOrFallback(action.payload.panX, state.viewbox.panX),
        panY: finiteNumberOrFallback(action.payload.panY, state.viewbox.panY),
      };
    },

    setDragging: (state, action: PayloadAction<boolean>) => {
      state.isDragging = action.payload;
    },

    clearCanvas: (state) => {
      state.objects = [];
      state.selectedIds = [];
      state.isDragging = false;
    },

    /**
     * Synchronisiert den kompletten State aus dem Fabric-Instanz-Serialisat.
     */
    syncFromFabric: (state, action: PayloadAction<CanvasObject[]>) => {
      state.objects = sortObjectsByZIndex(action.payload);
      const validIds = new Set(state.objects.map((object) => object.id));
      state.selectedIds = normalizeSelectedIds(state.selectedIds, validIds);
    },

    /**
     * Rehydriert den kompletten Canvas-State aus einem gespeicherten Mirror.
     * Ungültige oder alte Payloads werden normalisiert statt ungeprüft übernommen.
     */
    restoreCanvasState: (_state, action: PayloadAction<unknown>) => {
      const normalized = normalizeCanvasStateInput(action.payload);
      return normalized ?? getInitialCanvasState();
    },
  },
});

export const {
  addObject,
  addVectors,
  updateObject,
  removeObject,
  removeObjects,
  selectObjects,
  setZIndex,
  moveLayer,
  setViewbox,
  setDragging,
  clearCanvas,
  syncFromFabric,
  restoreCanvasState,
} = canvasSlice.actions;

export default canvasSlice.reducer;
