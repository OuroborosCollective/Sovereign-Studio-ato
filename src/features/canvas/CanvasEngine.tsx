import React, { useEffect, useRef } from 'react';
import { fabric } from 'fabric';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../../store/index';
import { 
  CanvasObject, 
  updateObject, 
  selectObjects 
} from './canvasSlice';

interface CanvasEngineProps {
  className?: string;
}

/**
 * Extended Fabric Canvas interface to include custom properties for panning/dragging.
 */
interface ExtendedCanvas extends fabric.Canvas {
  isDragging?: boolean;
  lastPosX?: number;
  lastPosY?: number;
}

/**
 * Extended Fabric Object interface to include custom properties like ID.
 */
interface ExtendedObject extends fabric.Object {
  id?: string;
}

const HW_ACCELERATION_STYLE: React.CSSProperties = {
  transform: 'translateZ(0)',
  backfaceVisibility: 'hidden',
  perspective: 1000,
  willChange: 'transform',
  WebkitFontSmoothing: 'antialiased',
};

export const CanvasEngine: React.FC<CanvasEngineProps> = ({ className }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fabricCanvasRef = useRef<ExtendedCanvas | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dispatch = useDispatch();
  
  const objects = useSelector((state: RootState) => state.canvas.objects);
  const selectedIds = useSelector((state: RootState) => state.canvas.selectedIds);
  const primarySelectedId = selectedIds.length > 0 ? selectedIds[0] : null;

  useEffect(() => {
    if (!canvasRef.current || !containerRef.current) return;

    fabric.Object.prototype.objectCaching = true;
    fabric.Object.prototype.noScaleCache = false;
    fabric.Object.prototype.transparentCorners = false;

    const fabricCanvas = new fabric.Canvas(canvasRef.current, {
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      backgroundColor: '#f8fafc',
      preserveObjectStacking: true,
      renderOnAddRemove: false,
    }) as ExtendedCanvas;

    fabricCanvasRef.current = fabricCanvas;

    fabricCanvas.on('mouse:wheel', (opt) => {
      const delta = opt.e.deltaY;
      let zoom = fabricCanvas.getZoom();
      zoom *= 0.999 ** delta;
      if (zoom > 20) zoom = 20;
      if (zoom < 0.01) zoom = 0.01;
      
      requestAnimationFrame(() => {
        fabricCanvas.zoomToPoint({ x: opt.e.offsetX, y: opt.e.offsetY }, zoom);
      });
      
      opt.e.preventDefault();
      opt.e.stopPropagation();
    });

    fabricCanvas.on('mouse:down', (opt) => {
      const evt = opt.e;
      if (evt.altKey === true) {
        fabricCanvas.isDragging = true;
        fabricCanvas.selection = false;
        fabricCanvas.lastPosX = evt.clientX;
        fabricCanvas.lastPosY = evt.clientY;
      }
    });

    fabricCanvas.on('mouse:move', (opt) => {
      if (fabricCanvas.isDragging) {
        const e = opt.e;
        const vpt = fabricCanvas.viewportTransform;
        if (vpt) {
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

    fabricCanvas.on('selection:created', (e) => {
      const activeObject = e.selected?.[0] as ExtendedObject;
      if (activeObject?.id) {
        dispatch(selectObjects([activeObject.id]));
      }
    });

    fabricCanvas.on('selection:updated', (e) => {
      const activeObject = e.selected?.[0] as ExtendedObject;
      if (activeObject?.id) {
        dispatch(selectObjects([activeObject.id]));
      }
    });

    fabricCanvas.on('selection:cleared', () => {
      dispatch(selectObjects([]));
    });

    const handleModified = (e: fabric.IEvent) => {
      const obj = e.target;
      if (!obj || !(obj as ExtendedObject).id) return;

      dispatch(updateObject({
        id: (obj as ExtendedObject).id,
        x: obj.left || 0,
        y: obj.top || 0,
        width: (obj.width || 0) * (obj.scaleX || 1),
        height: (obj.height || 0) * (obj.scaleY || 1),
      }));
    };

    fabricCanvas.on('object:modified', handleModified);

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
    };
  }, [dispatch]);

  useEffect(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const currentFabricObjects = canvas.getObjects();
    let hasChanges = false;
    
    // ⚡ Bolt: Replaced O(N²) nested loops with O(N) Map lookups
    const existingFabricObjectsMap = new Map<string, fabric.Object>();
    currentFabricObjects.forEach((fObj: ExtendedObject) => {
      if (fObj.id) {
        existingFabricObjectsMap.set(fObj.id, fObj);
      }
    });

    const reduxObjectIdsSet = new Set<string>();

    objects.forEach((objData, index) => {
      reduxObjectIdsSet.add(objData.id);
      const existingObj = existingFabricObjectsMap.get(objData.id);

      if (existingObj) {
        // ⚡ Bolt: Replace O(N²) nested loop indexOf with O(1) item access
        const needsUpdate = 
          existingObj.left !== objData.x || 
          existingObj.top !== objData.y || 
          (canvas.item(index) as unknown as ExtendedObject) !== existingObj;

        if (needsUpdate) {
          existingObj.set({ left: objData.x, top: objData.y });
          existingObj.setCoords();
          canvas.moveTo(existingObj, index);
          hasChanges = true;
        }
      } else {
        let newObj: fabric.Object;

        if (objData.type === 'ai-text') {
          newObj = new fabric.IText(objData.data.text || '', {
            left: objData.x,
            top: objData.y,
            fontSize: 16,
            fontFamily: 'Inter',
          });
        } else {
          newObj = new fabric.Rect({
            left: objData.x,
            top: objData.y,
            width: objData.width,
            height: objData.height,
            fill: objData.data.color || '#94a3b8',
            rx: 4,
            ry: 4,
          });
        }

        (newObj as ExtendedObject).id = objData.id;
        canvas.add(newObj);
        canvas.moveTo(newObj, index);
        hasChanges = true;
      }
    });

    currentFabricObjects.forEach((fObj: ExtendedObject) => {
      if (fObj.id && !reduxObjectIdsSet.has(fObj.id)) {
        canvas.remove(fObj);
        hasChanges = true;
      }
    });

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
        const target = canvas.getObjects().find((o: ExtendedObject) => o.id === primarySelectedId);
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
        ...HW_ACCELERATION_STYLE 
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