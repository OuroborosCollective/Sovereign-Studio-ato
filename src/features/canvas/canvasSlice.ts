import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export type FabricObjectType = 'rect' | 'circle' | 'path' | 'image' | 'i-text' | 'textbox' | 'group';

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
  originX?: string;
  originY?: string;
  zIndex: number;
  // Text properties
  text?: string;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: string | number;
  textAlign?: string;
  lineHeight?: number;
  charSpacing?: number;
  // Image properties
  src?: string;
  crossOrigin?: string;
  // Path properties
  path?: any[];
  // Metadata & Custom
  locked?: boolean;
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
}

const initialState: CanvasState = {
  objects: [],
  selectedIds: [],
  viewbox: {
    zoom: 1,
    panX: 0,
    panY: 0,
  },
};

export const canvasSlice = createSlice({
  name: 'canvas',
  initialState,
  reducers: {
    addObject: (state, action: PayloadAction<CanvasObject>) => {
      const exists = state.objects.some((obj) => obj.id === action.payload.id);
      if (!exists) {
        state.objects.push(action.payload);
        state.objects.sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
      }
    },
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
      const idsToRemove = action.payload;
      state.objects = state.objects.filter((obj) => !idsToRemove.includes(obj.id));
      state.selectedIds = state.selectedIds.filter((id) => !idsToRemove.includes(id));
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
    moveLayer: (state, action: PayloadAction<{ id: string; delta: number }>) => {
      const index = state.objects.findIndex((o) => o.id === action.payload.id);
      if (index === -1) return;
      
      const newIndex = Math.max(0, Math.min(state.objects.length - 1, index + action.payload.delta));
      const [removed] = state.objects.splice(index, 1);
      state.objects.splice(newIndex, 0, removed);
      
      state.objects.forEach((obj, i) => {
        obj.zIndex = i;
      });
    },
    setViewbox: (state, action: PayloadAction<Partial<CanvasState['viewbox']>>) => {
      state.viewbox = { ...state.viewbox, ...action.payload };
    },
    clearCanvas: (state) => {
      state.objects = [];
      state.selectedIds = [];
    },
    syncFromFabric: (state, action: PayloadAction<CanvasObject[]>) => {
      state.objects = action.payload.sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
    },
  },
});

export const {
  addObject,
  updateObject,
  removeObject,
  removeObjects,
  selectObjects,
  setZIndex,
  moveLayer,
  setViewbox,
  clearCanvas,
  syncFromFabric,
} = canvasSlice.actions;

export default canvasSlice.reducer;