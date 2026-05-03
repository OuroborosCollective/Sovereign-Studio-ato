import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';

interface Point {
  x: number;
  y: number;
}

interface CanvasObject {
  id: string;
  type: 'ai-text' | 'ai-shape' | 'ai-image';
  x: number;
  y: number;
  width: number;
  height: number;
  data: any;
}

interface CanvasEngineProps {
  initialObjects?: CanvasObject[];
  onObjectSelect?: (id: string | null) => void;
}

/**
 * Sovereign Studio Infinite Canvas Engine
 * Handhabt Rendering, Transformationen und KI-Objekt-Manipulation
 */
export const CanvasEngine: React.FC<CanvasEngineProps> = ({ 
  initialObjects = [], 
  onObjectSelect 
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // State für Transformation (Infinite Canvas)
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState<Point>({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [lastMousePos, setLastMousePos] = useState<Point>({ x: 0, y: 0 });
  
  // State für KI-generierte Objekte
  const [objects, setObjects] = useState<CanvasObject[]>(initialObjects);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Zeichnen des Canvas
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Reset Transformation und Clear
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Grid Hintergrund (Infinite Feel)
    const gridSize = 50 * scale;
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    
    const startX = offset.x % gridSize;
    const startY = offset.y % gridSize;

    for (let x = startX; x < canvas.width; x += gridSize) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvas.height);
    }
    for (let y = startY; y < canvas.height; y += gridSize) {
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
    }
    ctx.stroke();

    // Kamera-Transformation anwenden
    ctx.translate(offset.x, offset.y);
    ctx.scale(scale, scale);

    // Objekte rendern
    objects.forEach((obj) => {
      ctx.save();
      
      if (selectedId === obj.id) {
        ctx.strokeStyle = '#3b82f6';
        ctx.lineWidth = 2 / scale;
        ctx.strokeRect(obj.x - 4, obj.y - 4, obj.width + 8, obj.height + 8);
      }

      if (obj.type === 'ai-text') {
        ctx.fillStyle = '#1e293b';
        ctx.font = `${16}px Inter, sans-serif`;
        ctx.fillText(obj.data.text || '', obj.x, obj.y + 16);
      } else if (obj.type === 'ai-shape') {
        ctx.fillStyle = obj.data.color || '#94a3b8';
        ctx.fillRect(obj.x, obj.y, obj.width, obj.height);
      }

      ctx.restore();
    });
  }, [offset, scale, objects, selectedId]);

  // Effekt für Canvas-Resize und Loop
  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current && canvasRef.current) {
        canvasRef.current.width = containerRef.current.clientWidth;
        canvasRef.current.height = containerRef.current.clientHeight;
        render();
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    let animationFrameId: number;
    const loop = () => {
      render();
      animationFrameId = requestAnimationFrame(loop);
    };
    loop();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, [render]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 1 || (e.button === 0 && e.spaceKey)) {
      setIsPanning(true);
      setLastMousePos({ x: e.clientX, y: e.clientY });
    } else {
      // Hit Detection für Objekte
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      
      const mouseX = (e.clientX - rect.left - offset.x) / scale;
      const mouseY = (e.clientY - rect.top - offset.y) / scale;

      const hit = objects.find(obj => 
        mouseX >= obj.x && mouseX <= obj.x + obj.width &&
        mouseY >= obj.y && mouseY <= obj.y + obj.height
      );

      setSelectedId(hit?.id || null);
      if (onObjectSelect) onObjectSelect(hit?.id || null);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isPanning) {
      const dx = e.clientX - lastMousePos.x;
      const dy = e.clientY - lastMousePos.y;
      setOffset(prev => ({ x: prev.x + dx, y: prev.y + dy }));
      setLastMousePos({ x: e.clientX, y: e.clientY });
    }
  };

  const handleMouseUp = () => {
    setIsPanning(false);
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomIntensity = 0.001;
    const delta = -e.deltaY;
    const newScale = Math.min(Math.max(scale + delta * zoomIntensity, 0.1), 10);
    
    // Zoom zum Mauszeiger
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomFactor = newScale / scale;
    
    setOffset(prev => ({
      x: mouseX - (mouseX - prev.x) * zoomFactor,
      y: mouseY - (mouseY - prev.y) * zoomFactor
    }));
    setScale(newScale);
  };

  return (
    <div 
      ref={containerRef} 
      style={{ width: '100%', height: '100%', overflow: 'hidden', background: '#f8fafc', position: 'relative' }}
    >
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        style={{ display: 'block', cursor: isPanning ? 'grabbing' : 'default' }}
      />
      <div style={{ position: 'absolute', bottom: 20, right: 20, pointerEvents: 'none', background: 'rgba(255,255,255,0.8)', padding: '4px 8px', borderRadius: '4px', fontSize: '12px' }}>
        Zoom: {Math.round(scale * 100)}% | Pos: {Math.round(offset.x)}, {Math.round(offset.y)}
      </div>
    </div>
  );
};

export default CanvasEngine;