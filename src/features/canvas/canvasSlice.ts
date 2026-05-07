import { createSlice, PayloadAction } from '@reduxjs/toolkit';

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
  fill?: string | any;
  stroke?: string;
  strokeWidth?: number;
  originX?: 'left' | 'center' | 'right' | string;
  originY?: 'top' | 'center' | 'bottom' | string;
  zIndex: number;
  
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
  path?: any[];
  
  // Metadaten & Status für KI-Vorgänge
  locked?: boolean;
  aiGenerated?: boolean;
  promptSource?: string;
  metadata?: Record<string, unknown>;
  
  [key: string]: any;
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
      const existingIds = new Set(state.objects.map(obj => obj.id));
      action.payload.forEach((newObj) => {
        if (!existingIds.has(newObj.id)) {
          state.objects.push(newObj);
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
      state.objects = state.objects.filter((obj) => obj.id !== action.payload);
      state.selectedIds = state.selectedIds.filter((id) => id !== action.payload);
    },

    removeObjects: (state, action: PayloadAction<string[]>) => {
      const idsToRemove = new Set(action.payload);
      state.objects = state.objects.filter((obj) => !idsToRemove.has(obj.id));
      state.selectedIds = state.selectedIds.filter((id) => !idsToRemove.has(id));
    },

    selectObjects: (state, action: PayloadAction<string[]>) => {
      state.selectedIds = action.payload;
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
      
      const newIndex = Math.max(0, Math.min(state.objects.length - 1, index + action.payload.delta));
      const [removed] = state.objects.splice(index, 1);
      state.objects.splice(newIndex, 0, removed);
      
      // Normalisierung der Indizes für konsistente Rendering-Pipeline
      state.objects.forEach((obj, i) => {
        obj.zIndex = i;
      });
    },

    setViewbox: (state, action: PayloadAction<Partial<CanvasState['viewbox']>>) => {
      state.viewbox = { ...state.viewbox, ...action.payload };
    },

    setDragging: (state, action: PayloadAction<boolean>) => {
      state.isDragging = action.payload;
    },

    clearCanvas: (state) => {
      state.objects = [];
      state.selectedIds = [];
    },

    /**
     * Synchronisiert den kompletten State aus dem Fabric-Instanz-Serialisat.
     */
    syncFromFabric: (state, action: PayloadAction<CanvasObject[]>) => {
      state.objects = [...action.payload].sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
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
} = canvasSlice.actions;

export default canvasSlice.reducer;