/**
 * Sovereign Studio Mesh-System: Core EventBus
 * Zentraler EventEmitter für die agentenübergreifende Kommunikation und autonome Synchronisation.
 * Unterstützt den Build-to-Deploy Workflow durch Event-Tracing für den Ghost-Pilot.
 */

class EventBus {
  constructor() {
    this.events = new Map();
    this.traceEnabled = true;
  }

  /**
   * Registriert einen Listener für ein spezifisches Event.
   * @param {string} event - Der Name des Events.
   * @param {Function} callback - Die auszuführende Funktion.
   */
  on(event, callback) {
    if (!this.events.has(event)) {
      this.events.set(event, []);
    }
    this.events.get(event).push(callback);
    return () => this.off(event, callback);
  }

  /**
   * Registriert einen Listener, der nur einmalig ausgelöst wird.
   * @param {string} event 
   * @param {Function} callback 
   */
  once(event, callback) {
    const wrapper = (data) => {
      callback(data);
      this.off(event, wrapper);
    };
    return this.on(event, wrapper);
  }

  /**
   * Entfernt einen Listener.
   * @param {string} event 
   * @param {Function} callback 
   */
  off(event, callback) {
    if (!this.events.has(event)) return;
    const callbacks = this.events.get(event).filter(cb => cb !== callback);
    this.events.set(event, callbacks);
  }

  /**
   * Emittiert ein Event an alle registrierten Listener.
   * Integriert Tracing für die Gemini-KI-Ebene und den Autonomous-Cycle.
   * @param {string} event 
   * @param {any} data 
   */
  emit(event, data) {
    if (this.traceEnabled) {
      this._trace(event, data);
    }

    if (!this.events.has(event)) return;

    this.events.get(event).forEach(callback => {
      try {
        callback(data);
      } catch (error) {
        console.error(`[EventBus] Fehler im Listener für "${event}":`, error);
      }
    });
  }

  /**
   * Internes Tracing für die Überwachung des Agenten-Zustands.
   * Verwendet keine verbotenen Regex-Methoden.
   */
  _trace(event, data) {
    // Protokollierung für Ghost-Pilot Telemetrie
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] EVENT_BUS_EMIT: ${event}`;
    
    // In Produktions-Builds oder Capacitor-Umgebungen erfolgt hier die Weiterleitung an native Logs
    if (typeof window !== 'undefined' && window.Capacitor) {
      console.log(`${logEntry}`, data);
    }
  }

  /**
   * Bereinigt alle Listener (nützlich für HMR im Vite-Stack).
   */
  clear() {
    this.events.clear();
  }
}

// Singleton-Instanz für globale Verfügbarkeit im Mesh
const eventBus = new EventBus();

export default eventBus;