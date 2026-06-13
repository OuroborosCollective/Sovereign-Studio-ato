import React, { useEffect, useRef } from 'react';
import { Canvas, FabricObject, IText, Point, Rect } from 'fabric';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../../store/index';
import {
  updateObject,
  selectObjects,
} from './canvasSlice';

type ExtendedCanvas = Canvas & {
  isDragging?: boolean;
  lastPosX?: number;
  lastPosY?: number;
  selection?: boolean;
  viewportTransform?: number[];
};

type ExtendedObject = FabricObject & {
  id?: string;
};

interface CanvasEngineProps {
  className?: string;
}

const HW_ACCELERATION_STYLE: React.CSSProperties = {
  transform: 'translateZ(0)',
  backfaceVisibility: 'hidden',
  perspective: 1000,
  willChange: 'transform',
  WebkitFontSmoothing: 'antialiased',
};

const moveObjectToLayer = (canvas: ExtendedCanvas, object: FabricObject, index: number) => {
  const compatCanvas = canvas as unknown as {
    moveObjectTo?: (object: FabricObject, index: number) => void;
    moveTo?: (object: FabricObject, index: number) => void;
  };

  if (typeof compatCanvas.moveObjectTo === 'function') {
    compatCanvas.moveObjectTo(object, index);
    return;
  }

  if (typeof compatCanvas.moveTo === 'function') {
    compatCanvas.moveTo(object, index);
  }
};

export const CanvasEngine: React.FC<CanvasEngineProps> = ({ className }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fabricCanvasRef = useRef<ExtendedCanvas | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dispatch = useDispatch();

  const objects = useSelector((state: RootState) => state.canvas.objects);
  const selectedIds = useSelector((state: RootState) => state.canvas.selectedIds);
  const primarySelectedId = selectedIds.length > 0 ? selectedIds[0] : null;

  const fabricObjectsMapRef = useRef<Map<string, FabricObject>>(new Map());

  useEffect(() => {
    if (!canvasRef.current || !containerRef.current) return;

    const fabricObjectDefaults = FabricObject.prototype as unknown as {
      objectCaching?: boolean;
      noScaleCache?: boolean;
      transparentCorners?: boolean;
    };
    fabricObjectDefaults.objectCaching = true;
    fabricObjectDefaults.noScaleCache = false;
    fabricObjectDefaults.transparentCorners = false;

    const fabricCanvas = new Canvas(canvasRef.current, {
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      backgroundColor: '#f8fafc',
      preserveObjectStacking: true,
      renderOnAddRemove: false,
    }) as ExtendedCanvas;

    fabricCanvasRef.current = fabricCanvas;

    fabricCanvas.on('mouse:wheel', (opt: any) => {
      const delta = opt.e.deltaY;
      let zoom = fabricCanvas.getZoom();
      zoom *= 0.999 ** delta;
      if (zoom > 20) zoom = 20;
      if (zoom < 0.01) zoom = 0.01;

      requestAnimationFrame(() => {
        fabricCanvas.zoomToPoint(new Point(opt.e.offsetX, opt.e.offsetY), zoom);
      });

      opt.e.preventDefault();
      opt.e.stopPropagation();
    });

    fabricCanvas.on('mouse:down', (opt: any) => {
      const evt = opt.e;
      if (evt.altKey === true) {
        fabricCanvas.isDragging = true;
        fabricCanvas.selection = false;
        fabricCanvas.lastPosX = evt.clientX;
        fabricCanvas.lastPosY = evt.clientY;
      }
    });

    fabricCanvas.on('mouse:move', (opt: any) => {
      if (fabricCanvas.isDragging) {
        const e = opt.e;
        const vpt = fabricCanvas.viewportTransform;
        if (vpt && fabricCanvas.lastPosX !== undefined && fabricCanvas.lastPosY !== undefined) {
          vpt[4] += e.clientX - fabricCanvas.lastPosX;
          vpt[5] += e.clientY - fabricCanvas.lastPosY;
          fabricCanvas.requestRenderAll();
          fabricCanvas.lastPosX = e.clientX;
          fabricCanvas.lastPosY = e.clientY;
        }
      }
    });

    fabricCanvas.on('mouse:up', () => {
      fabricCanvas.setViewportTransform(fabricCanvas.viewportTransform || [1, 0, 0, 1, 0, 0]);
      fabricCanvas.isDragging = false;
      fabricCanvas.selection = true;
    });

    fabricCanvas.on('selection:created', (e: any) => {
      const activeObject = e.selected?.[0] as ExtendedObject;
      if (activeObject?.id) {
        dispatch(selectObjects([activeObject.id]));
      }
    });

    fabricCanvas.on('selection:updated', (e: any) => {
      const activeObject = e.selected?.[0] as ExtendedObject;
      if (activeObject?.id) {
        dispatch(selectObjects([activeObject.id]));
      }
    });

    fabricCanvas.on('selection:cleared', () => {
      dispatch(selectObjects([]));
    });

    const handleModified = (e: { target?: FabricObject }) => {
      const obj = e.target;
      if (!obj || !(obj as ExtendedObject).id) return;

      dispatch(updateObject({
        id: (obj as ExtendedObject).id!,
        x: obj.left || 0,
        y: obj.top || 0,
        width: (obj.width || 0) * (obj.scaleX || 1),
        height: (obj.height || 0) * (obj.scaleY || 1),
      }));
    };

    fabricCanvas.on('object:modified', handleModified as any);

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current && fabricCanvasRef.current) {
        const width = containerRef.current.clientWidth;
        const height = containerRef.current.clientHeight;
        requestAnimationFrame(() => {
          fabricCanvasRef.current?.setDimensions({ width, height });
        });
      }
    });

    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      fabricCanvas.dispose();
      fabricObjectsMapRef.current.clear();
    };
  }, [dispatch]);

  useEffect(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const currentFabricObjects = canvas.getObjects();
    let hasChanges = false;

    const existingFabricObjectsMap = fabricObjectsMapRef.current;
    const reduxObjectIdsSet = new Set<string>();

    for (let index = 0; index < objects.length; index++) {
      const objData = objects[index];
      reduxObjectIdsSet.add(objData.id);
      const existingObj = existingFabricObjectsMap.get(objData.id);

      if (existingObj) {
        const isAtCorrectIndex = currentFabricObjects[index] === existingObj;
        const needsUpdate =
          existingObj.left !== objData.x ||
          existingObj.top !== objData.y ||
          !isAtCorrectIndex;

        if (needsUpdate) {
          existingObj.set({ left: objData.x, top: objData.y });
          existingObj.setCoords();
          if (!isAtCorrectIndex) {
            moveObjectToLayer(canvas, existingObj, index);
          }
          hasChanges = true;
        }
      } else {
        let newObj: FabricObject;

        if (objData.type === 'ai-text') {
          newObj = new IText((objData.data as any).text || '', {
            left: objData.x,
            top: objData.y,
            fontSize: 16,
            fontFamily: 'Inter',
          });
        } else {
          newObj = new Rect({
            left: objData.x,
            top: objData.y,
            width: objData.width,
            height: objData.height,
            fill: (objData.data as any).color || '#94a3b8',
            rx: 4,
            ry: 4,
          });
        }

        (newObj as ExtendedObject).id = objData.id;
        canvas.add(newObj);
        moveObjectToLayer(canvas, newObj, index);

        existingFabricObjectsMap.set(objData.id, newObj);
        hasChanges = true;
      }
    }

    // Remove objects that are no longer in the Redux state
    for (const [id, fObj] of existingFabricObjectsMap.entries()) {
      if (!reduxObjectIdsSet.has(id)) {
        canvas.remove(fObj);
        existingFabricObjectsMap.delete(id);
        hasChanges = true;
      }
    }

    if (hasChanges) {
      canvas.requestRenderAll();
    }
  }, [objects]);

  useEffect(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject() as ExtendedObject;

    if (primarySelectedId) {
      if (!activeObj || activeObj.id !== primarySelectedId) {
        const objs = canvas.getObjects();
        let target = undefined;
        for (let i = 0; i < objs.length; i++) {
          if ((objs[i] as ExtendedObject).id === primarySelectedId) {
            target = objs[i];
            break;
          }
        }
        if (target) {
          canvas.setActiveObject(target);
          canvas.requestRenderAll();
        }
      }
    } else if (activeObj) {
      canvas.discardActiveObject();
      canvas.requestRenderAll();
    }
  }, [primarySelectedId]);

  return (
    <div
      ref={containerRef}
      className={`w-full h-full overflow-hidden relative bg-slate-50 ${className || ''}`}
      style={{
        minHeight: '400px',
        ...HW_ACCELERATION_STYLE,
      }}
    >
      <canvas
        ref={canvasRef}
        style={HW_ACCELERATION_STYLE}
      />
    </div>
  );
};

export default CanvasEngine;
