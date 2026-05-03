import React, { useEffect, useRef, useMemo } from 'react';
import { fabric } from 'fabric';
import { useDispatch, useSelector } from 'react-redux';

interface CanvasObject {
  id: string;
  type: 'ai-text' | 'ai-shape' | 'ai-image';
  x: number;
  y: number;
  width: number;
  height: number;
  data: any;
}

interface RootState {
  canvas: {
    objects: CanvasObject[];
    selectedId: string | null;
  };
}

const updateObject = (payload: Partial<CanvasObject> & { id: string }) => ({ type: 'canvas/updateObject', payload });
const selectObject = (id: string | null) => ({ type: 'canvas/selectObject', payload: id });

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

export const CanvasEngine: React.FC<CanvasEngineProps> = ({ className }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fabricCanvasRef = useRef<fabric.Canvas | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dispatch = useDispatch();
  
  const objects = useSelector((state: RootState) => state.canvas.objects);
  const selectedId = useSelector((state: RootState) => state.canvas.selectedId);

  useEffect(() => {
    if (!canvasRef.current || !containerRef.current) return;

    // Globale Fabric Optimierungen für WebView Low-Latency
    fabric.Object.prototype.objectCaching = true;
    fabric.Object.prototype.noScaleCache = false;
    fabric.Object.prototype.transparentCorners = false;

    const fabricCanvas = new fabric.Canvas(canvasRef.current, {
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      backgroundColor: '#f8fafc',
      preserveObjectStacking: true,
      renderOnAddRemove: false, // Optimierter Batch-Render
      statefullCache: true,
    });

    fabricCanvasRef.current = fabricCanvas;

    // Zoom-Handler (Infinite Canvas Feeling) mit rAF Optimierung
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
      const activeObject = e.selected?.[0] as any;
      if (activeObject?.id) dispatch(selectObject(activeObject.id));
    });

    fabricCanvas.on('selection:cleared', () => {
      dispatch(selectObject(null));
    });

    const handleModified = (e: fabric.IEvent) => {
      const obj = e.target;
      if (!obj || !(obj as any).id) return;

      dispatch(updateObject({
        id: (obj as any).id,
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
    
    objects.forEach((objData) => {
      const existingObj = currentFabricObjects.find((o: any) => o.id === objData.id);

      if (existingObj) {
        if (existingObj.left !== objData.x || existingObj.top !== objData.y) {
          existingObj.set({ left: objData.x, top: objData.y });
          existingObj.setCoords();
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

        (newObj as any).id = objData.id;
        canvas.add(newObj);
        hasChanges = true;
      }
    });

    currentFabricObjects.forEach((fObj: any) => {
      if (!objects.find(o => o.id === fObj.id)) {
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

    const activeObj = canvas.getActiveObject() as any;
    if (selectedId && (!activeObj || activeObj.id !== selectedId)) {
      const target = canvas.getObjects().find((o: any) => o.id === selectedId);
      if (target) {
        canvas.setActiveObject(target);
        canvas.requestRenderAll();
      }
    } else if (!selectedId && activeObj) {
      canvas.discardActiveObject();
      canvas.requestRenderAll();
    }
  }, [selectedId]);

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