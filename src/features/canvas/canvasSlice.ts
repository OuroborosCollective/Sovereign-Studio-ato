import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export type CanvasObjectType = 'vector' | 'image' | 'text';

export interface VectorData {
  path: string;
  fill?: string;
  stroke?: string;
  strokeWidth?: number;
}

export interface ImageData {
  src: string;
  originalWidth: number;
  originalHeight: number;
}

export interface TextData {
  content: string;
  fontSize: number;
  fontFamily: string;
  fontWeight: string | number;
  color: string;
  textAlign: 'left' | 'center' | 'right';
}

export interface CanvasObject {
  id: string;
  type: CanvasObjectType;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  scaleX: number;
  scaleY: number;
  opacity: number;
  zIndex: number;
  isVisible: boolean;
  isLocked: boolean;
  data: VectorData | ImageData | TextData;
  metadata?: Record<string, unknown>;
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
      state.objects.push(action.payload);
      state.objects.sort((a, b) => a.zIndex - b.zIndex);
    },
    updateObject: (state, action: PayloadAction<Partial<CanvasObject> & { id: string }>) => {
      const index = state.objects.findIndex((obj) => obj.id === action.payload.id);
      if (index !== -1) {
        state.objects[index] = { ...state.objects[index], ...action.payload };
        if (action.payload.zIndex !== undefined) {
          state.objects.sort((a, b) => a.zIndex - b.zIndex);
        }
      }
    },
    removeObjects: (state, action: PayloadAction<string[]>) => {
      state.objects = state.objects.filter((obj) => !action.payload.includes(obj.id));
      state.selectedIds = state.selectedIds.filter((id) => !action.payload.includes(id));
    },
    selectObjects: (state, action: PayloadAction<string[]>) => {
      state.selectedIds = action.payload;
    },
    setZIndex: (state, action: PayloadAction<{ id: string; zIndex: number }>) => {
      const obj = state.objects.find((o) => o.id === action.payload.id);
      if (obj) {
        obj.zIndex = action.payload.zIndex;
        state.objects.sort((a, b) => a.zIndex - b.zIndex);
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
  },
});

export const {
  addObject,
  updateObject,
  removeObjects,
  selectObjects,
  setZIndex,
  moveLayer,
  setViewbox,
  clearCanvas,
} = canvasSlice.actions;

export default canvasSlice.reducer;