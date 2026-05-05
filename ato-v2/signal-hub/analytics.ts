import { Device } from '@capacitor/device';

export interface PerformanceMetric {
  id: string;
  name: 'LCP' | 'FID' | 'CLS' | 'TBT' | 'API_LATENCY';
  value: number;
  threshold: number;
  timestamp: number;
  metadata?: Record<string, any>;
}

export interface UXFrictionSignal {
  type: 'RAGE_CLICK' | 'DEAD_CLICK' | 'EXCESSIVE_SCROLLING' | 'SLOW_NAVIGATION';
  elementId?: string;
  severity: 'low' | 'medium' | 'high';
  context: string;
}

export interface TaskTrigger {
  id: string;
  source: 'analytics-processor';
  priority: number;
  actionRequired: string;
  payload: any;
}

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

  public static getInstance(): AnalyticsProcessor {
    if (!AnalyticsProcessor.instance) {
      AnalyticsProcessor.instance = new AnalyticsProcessor();
    }
    return AnalyticsProcessor.instance;
  }

  private initPerformanceObserver(): void {
    if (typeof window === 'undefined' || !window.PerformanceObserver) return;

    const observer = new PerformanceObserver((list) => {
      list.getEntries().forEach((entry) => {
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

    observer.observe({ type: 'largest-contentful-paint', buffered: true });
  }

  private initInteractionListeners(): void {
    if (typeof window === 'undefined') return;

    window.addEventListener('click', (e: MouseEvent) => {
      const target = (e.target as HTMLElement).tagName || 'unknown';
      this.detectUXFriction(e.clientX, e.clientY, target);
    });
  }

  private detectUXFriction(x: number, y: number, target: string): void {
    const now = Date.now();
    this.clickHistory.push({ x, y, time: now, target });

    // Clean old clicks
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
        this.clickHistory = [];
      }
    }
  }

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
  }

  private async evaluateMetric(metric: PerformanceMetric): Promise<void> {
    if (metric.value > metric.threshold) {
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
    }
    this.metricsBuffer.push(metric);
  }

  private emitTaskTrigger(trigger: TaskTrigger): void {
    // Dispatch to Signal Hub / Gemini Orchestrator
    const event = new CustomEvent('sovereign:task_trigger', { detail: trigger });
    window.dispatchEvent(event);
    
    console.debug(`[AnalyticsProcessor] Trigger generated: ${trigger.actionRequired}`, trigger.payload);
  }

  public getRecentMetrics(): PerformanceMetric[] {
    return [...this.metricsBuffer].slice(-50);
  }
}

export const analyticsProcessor = AnalyticsProcessor.getInstance();