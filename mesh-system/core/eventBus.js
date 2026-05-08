/**
 * Sovereign Studio Mesh-System: Core EventBus
 * Zentraler EventEmitter für die agentenübergreifende Kommunikation und autonome Synchronisation.
 * Integriert die GitHub-API-Bridge zur Schließung der autonomen Ghost-Pilot-Schleife.
 */

class EventBus {
  constructor() {
    this.events = new Map();
    this.traceEnabled = true;
    this._initGitHubBridge();
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
   * Initialisiert die GitHub-Bridge für die autonome Workflow-Steuerung.
   * Registriert den Listener für 'POST_SECURITY_CLEARED'.
   */
  _initGitHubBridge() {
    this.on('POST_SECURITY_CLEARED', async (payload) => {
      console.log('[EventBus] Security Cleared. Initiiere Ghost-Pilot Deployment...');
      await this._triggerGitHubDispatch('ghost-pilot', payload);
    });
  }

  /**
   * Sendet einen Repository Dispatch an GitHub, um die agentische Kette fortzuführen.
   * @param {string} eventType 
   * @param {object} payload 
   */
  async _triggerGitHubDispatch(eventType, payload) {
    const GITHUB_TOKEN = import.meta.env.VITE_GH_TOKEN || process.env.VITE_GH_TOKEN;
    const REPO_OWNER_NAME = import.meta.env.VITE_GH_REPO || process.env.VITE_GH_REPO; // Format: "owner/repo"

    if (!GITHUB_TOKEN || !REPO_OWNER_NAME) {
      console.warn('[EventBus] GitHub-Bridge übersprungen: Fehlende Zugangsdaten.');
      return;
    }

    try {
      const response = await fetch(`https://api.github.com/repos/${REPO_OWNER_NAME}/dispatches`, {
        method: 'POST',
        headers: {
          'Accept': 'application/vnd.github.v3+json',
          'Authorization': `Bearer ${GITHUB_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          event_type: eventType,
          client_payload: {
            timestamp: new Date().toISOString(),
            origin: 'EventBus-Mesh-Core',
            context: payload
          }
        })
      });

      if (response.ok) {
        console.log(`[EventBus] GitHub Workflow "${eventType}" erfolgreich getriggert.`);
      } else {
        const errorText = await response.text();
        console.error(`[EventBus] GitHub API Fehler: ${response.status} - ${errorText}`);
      }
    } catch (err) {
      console.error('[EventBus] GitHub Dispatch Exception:', err);
    }
  }

  /**
   * Internes Tracing für die Überwachung des Agenten-Zustands.
   */
  _trace(event, data) {
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] EVENT_BUS_EMIT: ${event}`;
    
    if (typeof window !== 'undefined' && window.Capacitor) {
      console.log(`${logEntry}`, data);
    } else {
      // Standard Node/Vite Log für Entwicklung
      console.debug(logEntry, data);
    }
  }

  /**
   * Bereinigt alle Listener.
   */
  clear() {
    this.events.clear();
  }
}

// Singleton-Instanz für globale Verfügbarkeit im Mesh
const eventBus = new EventBus();

export default eventBus;