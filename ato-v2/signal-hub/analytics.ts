import { Device } from '@capacitor/device';

/**
 * Interface für Performance-Metriken (Web Vitals + API)
 */
export interface PerformanceMetric {
  id: string;
  name: 'LCP' | 'FID' | 'CLS' | 'TBT' | 'API_LATENCY';
  value: number;
  threshold: number;
  timestamp: number;
  metadata?: Record<string, any>;
}

/**
 * Interface für UX-Friction-Signale (Benutzerfrustration)
 */
export interface UXFrictionSignal {
  type: 'RAGE_CLICK' | 'DEAD_CLICK' | 'EXCESSIVE_SCROLLING' | 'SLOW_NAVIGATION';
  elementId?: string;
  severity: 'low' | 'medium' | 'high';
  context: string;
}

/**
 * Interface für Task-Trigger, die an den Gemini Orchestrator gesendet werden
 */
export interface TaskTrigger {
  id: string;
  source: 'analytics-processor';
  priority: number;
  actionRequired: string;
  payload: any;
}

/**
 * AnalyticsProcessor: Überwacht Performance und UX-Friction autonom.
 * Teil des Sovereign Studio Signal-Hubs zur Selbstoptimierung der Anwendung.
 */
class AnalyticsProcessor {
  private static instance: AnalyticsProcessor;
  private metricsBuffer: PerformanceMetric[] = [];
  private clickHistory: { x: number; y: number; time: number; target: string }[] = [];
  
  private readonly RAGE_CLICK_THRESHOLD = 5; 
  private readonly RAGE_CLICK_WINDOW = 1000;
  private readonly API_LATENCY_THRESHOLD = 800;

  private constructor() {
    this.initPerformanceObserver();
    this.initInteractionListeners();
  }

  /**
   * Singleton-Instanz des AnalyticsProcessors
   */
  public static getInstance(): AnalyticsProcessor {
    if (!AnalyticsProcessor.instance) {
      AnalyticsProcessor.instance = new AnalyticsProcessor();
    }
    return AnalyticsProcessor.instance;
  }

  /**
   * Initialisiert PerformanceObserver für Web Vitals (LCP)
   */
  private initPerformanceObserver(): void {
    if (typeof window === 'undefined' || !window.PerformanceObserver) return;

    const observer = new PerformanceObserver((list) => {
      list.getEntries().forEach((entry) => {
        // Largest Contentful Paint Überwachung
        if (entry.entryType === 'largest-contentful-paint') {
          this.evaluateMetric({
            id: crypto.randomUUID(),
            name: 'LCP',
            value: entry.startTime,
            threshold: 2500,
            timestamp: Date.now()
          });
        }
      });
    });

    try {
      // buffered: true erlaubt den Zugriff auf Metriken vor der Observer-Initialisierung
      observer.observe({ type: 'largest-contentful-paint', buffered: true });
    } catch (e) {
      console.warn('[AnalyticsProcessor] LCP observer not supported or failed', e);
    }
  }

  /**
   * Registriert Event-Listener für Benutzerinteraktionen zur Frustrationserkennung
   */
  private initInteractionListeners(): void {
    if (typeof window === 'undefined') return;

    window.addEventListener('click', (e: MouseEvent) => {
      const target = (e.target as HTMLElement).tagName || 'unknown';
      this.detectUXFriction(e.clientX, e.clientY, target);
    });
  }

  /**
   * Erkennt "Rage Clicks" (häufiges Klicken auf engem Raum)
   */
  private detectUXFriction(x: number, y: number, target: string): void {
    const now = Date.now();
    this.clickHistory.push({ x, y, time: now, target });

    // Alte Klicks aus dem Zeitfenster entfernen
    this.clickHistory = this.clickHistory.filter(c => now - c.time < this.RAGE_CLICK_WINDOW);

    if (this.clickHistory.length >= this.RAGE_CLICK_THRESHOLD) {
      const isSameArea = this.clickHistory.every(c => 
        Math.abs(c.x - x) < 20 && Math.abs(c.y - y) < 20
      );

      if (isSameArea) {
        this.emitTaskTrigger({
          id: `friction_${now}`,
          source: 'analytics-processor',
          priority: 0.8,
          actionRequired: 'OPTIMIZE_INTERACTION_FEEDBACK',
          payload: { type: 'RAGE_CLICK', target, count: this.clickHistory.length }
        });
        // Historie nach Erkennung leeren
        this.clickHistory = [];
      }
    }
  }

  /**
   * Protokolliert API-Latenzen und triggert bei Überschreitung Optimierungs-Tasks
   */
  public trackApiLatency(endpoint: string, duration: number): void {
    if (duration > this.API_LATENCY_THRESHOLD) {
      this.emitTaskTrigger({
        id: `perf_${Date.now()}`,
        source: 'analytics-processor',
        priority: 0.9,
        actionRequired: 'OPTIMIZE_API_ENDPOINT',
        payload: { endpoint, duration, threshold: this.API_LATENCY_THRESHOLD }
      });
    }
    
    this.metricsBuffer.push({
      id: crypto.randomUUID(),
      name: 'API_LATENCY',
      value: duration,
      threshold: this.API_LATENCY_THRESHOLD,
      timestamp: Date.now(),
      metadata: { endpoint }
    });
  }

  /**
   * Evaluiert Metriken gegen Grenzwerte und reichert Daten mit Geräte-Infos an
   */
  private async evaluateMetric(metric: PerformanceMetric): Promise<void> {
    if (metric.value > metric.threshold) {
      try {
        const deviceInfo = await Device.getInfo();
        
        this.emitTaskTrigger({
          id: `metric_${metric.id}`,
          source: 'analytics-processor',
          priority: 0.7,
          actionRequired: 'INVESTIGATE_PERFORMANCE_REGRESSION',
          payload: { 
            metric: metric.name, 
            value: metric.value, 
            platform: deviceInfo.platform,
            osVersion: deviceInfo.osVersion 
          }
        });
      } catch (err) {
        console.error('[AnalyticsProcessor] Could not fetch device info', err);
      }
    }
    this.metricsBuffer.push(metric);
  }

  /**
   * Sendet ein Signal an das Sovereign Studio System-Event-System
   */
  private emitTaskTrigger(trigger: TaskTrigger): void {
    if (typeof window === 'undefined') return;

    const event = new CustomEvent('sovereign:task_trigger', { detail: trigger });
    window.dispatchEvent(event);
    
    console.debug(`[AnalyticsProcessor] Trigger generated: ${trigger.actionRequired}`, trigger.payload);
  }

  /**
   * Gibt die letzten Metriken für UI-Dashboards zurück
   */
  public getRecentMetrics(): PerformanceMetric[] {
    return [...this.metricsBuffer].slice(-50);
  }
}

export const analyticsProcessor = AnalyticsProcessor.getInstance();