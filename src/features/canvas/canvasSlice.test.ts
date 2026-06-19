import { describe, it, expect } from 'vitest';
import reducer, {
  moveLayer,
  addObject,
  addVectors,
  updateObject,
  removeObject,
  removeObjects,
  selectObjects,
  setZIndex,
  setViewbox,
  setDragging,
  clearCanvas,
  syncFromFabric,
  CanvasState,
  CanvasObject
} from './canvasSlice';

const createMockObject = (id: string, zIndex: number): CanvasObject => ({
  id,
  type: 'rect',
  left: 0,
  top: 0,
  width: 100,
  height: 100,
  scaleX: 1,
  scaleY: 1,
  angle: 0,
  flipX: false,
  flipY: false,
  opacity: 1,
  visible: true,
  zIndex,
});

describe('canvasSlice reducers', () => {
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

  describe('moveLayer', () => {
    it('should move a layer forward (up in hierarchy)', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [
          createMockObject('1', 0),
          createMockObject('2', 1),
          createMockObject('3', 2),
        ],
      };

      const action = moveLayer({ id: '1', delta: 1 });
      const nextState = reducer(state, action);

      expect(nextState.objects[0].id).toBe('2');
      expect(nextState.objects[1].id).toBe('1');
      expect(nextState.objects[2].id).toBe('3');

      // Verify zIndex normalization
      expect(nextState.objects[0].zIndex).toBe(0);
      expect(nextState.objects[1].zIndex).toBe(1);
      expect(nextState.objects[2].zIndex).toBe(2);
    });

    it('should move a layer backward (down in hierarchy)', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [
          createMockObject('1', 0),
          createMockObject('2', 1),
          createMockObject('3', 2),
        ],
      };

      const action = moveLayer({ id: '3', delta: -1 });
      const nextState = reducer(state, action);

      expect(nextState.objects[0].id).toBe('1');
      expect(nextState.objects[1].id).toBe('3');
      expect(nextState.objects[2].id).toBe('2');

      expect(nextState.objects[0].zIndex).toBe(0);
      expect(nextState.objects[1].zIndex).toBe(1);
      expect(nextState.objects[2].zIndex).toBe(2);
    });

    it('should clamp delta to top bound', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [
          createMockObject('1', 0),
          createMockObject('2', 1),
          createMockObject('3', 2),
        ],
      };

      const action = moveLayer({ id: '1', delta: 10 });
      const nextState = reducer(state, action);

      expect(nextState.objects[2].id).toBe('1');
      expect(nextState.objects[2].zIndex).toBe(2);
    });

    it('should clamp delta to bottom bound', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [
          createMockObject('1', 0),
          createMockObject('2', 1),
          createMockObject('3', 2),
        ],
      };

      const action = moveLayer({ id: '3', delta: -10 });
      const nextState = reducer(state, action);

      expect(nextState.objects[0].id).toBe('3');
      expect(nextState.objects[0].zIndex).toBe(0);
    });

    it('should do nothing if id is not found', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [
          createMockObject('1', 0),
        ],
      };

      const action = moveLayer({ id: 'unknown', delta: 1 });
      const nextState = reducer(state, action);

      expect(nextState).toEqual(state);
    });
  });

  describe('addObject', () => {
    it('should add a new object and sort by zIndex', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 10)],
      };

      const newObj = createMockObject('2', 5);
      const action = addObject(newObj);
      const nextState = reducer(state, action);

      expect(nextState.objects).toHaveLength(2);
      expect(nextState.objects[0].id).toBe('2');
      expect(nextState.objects[1].id).toBe('1');
    });

    it('should not add duplicate objects', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 0)],
      };

      const action = addObject(createMockObject('1', 10));
      const nextState = reducer(state, action);

      expect(nextState.objects).toHaveLength(1);
      expect(nextState.objects[0].zIndex).toBe(0);
    });
  });

  describe('addVectors', () => {
    it('should add multiple objects and sort by zIndex', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 10)],
      };

      const vectors = [
        createMockObject('2', 5),
        createMockObject('3', 15),
      ];
      const action = addVectors(vectors);
      const nextState = reducer(state, action);

      expect(nextState.objects).toHaveLength(3);
      expect(nextState.objects[0].id).toBe('2');
      expect(nextState.objects[1].id).toBe('1');
      expect(nextState.objects[2].id).toBe('3');
    });

    it('should skip existing objects in batch addition', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 0)],
      };

      const vectors = [
        createMockObject('1', 10),
        createMockObject('2', 5),
      ];
      const action = addVectors(vectors);
      const nextState = reducer(state, action);

      expect(nextState.objects).toHaveLength(2);
      expect(nextState.objects.find(o => o.id === '1')?.zIndex).toBe(0);
    });
  });

  describe('removeObject', () => {
    it('should remove object from objects and selectedIds', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 0), createMockObject('2', 1)],
        selectedIds: ['1', '2'],
      };

      const action = removeObject('1');
      const nextState = reducer(state, action);

      expect(nextState.objects).toHaveLength(1);
      expect(nextState.objects[0].id).toBe('2');
      expect(nextState.selectedIds).toEqual(['2']);
    });
  });

  describe('removeObjects', () => {
    it('should remove multiple objects', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [
          createMockObject('1', 0),
          createMockObject('2', 1),
          createMockObject('3', 2),
        ],
        selectedIds: ['1', '2', '3'],
      };

      const action = removeObjects(['1', '3']);
      const nextState = reducer(state, action);

      expect(nextState.objects).toHaveLength(1);
      expect(nextState.objects[0].id).toBe('2');
      expect(nextState.selectedIds).toEqual(['2']);
    });
  });

  describe('selectObjects', () => {
    it('should update selectedIds', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [
          createMockObject('2', 0),
          createMockObject('3', 1),
        ],
        selectedIds: ['1'],
      };
      const action = selectObjects(['2', '3']);
      const nextState = reducer(state, action);
      expect(nextState.selectedIds).toEqual(['2', '3']);
    });

    it('should filter out non-existent object ids', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 0)],
        selectedIds: [],
      };
      const action = selectObjects(['1', 'nonexistent']);
      const nextState = reducer(state, action);
      expect(nextState.selectedIds).toEqual(['1']);
    });
  });

  describe('updateObject', () => {
    it('should update object properties', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 0)],
      };

      const action = updateObject({ id: '1', left: 100, top: 200 });
      const nextState = reducer(state, action);

      expect(nextState.objects[0].left).toBe(100);
      expect(nextState.objects[0].top).toBe(200);
    });

    it('should sort objects if zIndex is updated', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 0), createMockObject('2', 10)],
      };

      const action = updateObject({ id: '1', zIndex: 20 });
      const nextState = reducer(state, action);

      expect(nextState.objects[0].id).toBe('2');
      expect(nextState.objects[1].id).toBe('1');
    });
  });

  describe('setZIndex', () => {
    it('should update zIndex and sort', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 0), createMockObject('2', 10)],
      };

      const action = setZIndex({ id: '1', zIndex: 20 });
      const nextState = reducer(state, action);

      expect(nextState.objects[0].id).toBe('2');
      expect(nextState.objects[1].id).toBe('1');
      expect(nextState.objects[1].zIndex).toBe(20);
    });
  });

  describe('setViewbox', () => {
    it('should update viewbox partially', () => {
      const action = setViewbox({ zoom: 2 });
      const nextState = reducer(initialState, action);
      expect(nextState.viewbox.zoom).toBe(2);
      expect(nextState.viewbox.panX).toBe(0);
    });
  });

  describe('setDragging', () => {
    it('should update dragging state', () => {
      const action = setDragging(true);
      const nextState = reducer(initialState, action);
      expect(nextState.isDragging).toBe(true);
    });
  });

  describe('clearCanvas', () => {
    it('should clear objects and selectedIds', () => {
      const state: CanvasState = {
        ...initialState,
        objects: [createMockObject('1', 0)],
        selectedIds: ['1'],
      };
      const nextState = reducer(state, clearCanvas());
      expect(nextState.objects).toHaveLength(0);
      expect(nextState.selectedIds).toHaveLength(0);
    });
  });

  describe('syncFromFabric', () => {
    it('should sync objects and sort by zIndex', () => {
      const newObjects = [
        createMockObject('2', 10),
        createMockObject('1', 0),
      ];
      const nextState = reducer(initialState, syncFromFabric(newObjects));
      expect(nextState.objects).toHaveLength(2);
      expect(nextState.objects[0].id).toBe('1');
      expect(nextState.objects[1].id).toBe('2');
    });
  });
});
