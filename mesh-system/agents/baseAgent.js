import { EventBus } from '../core/eventBus.js';

/**
 * BaseAgent
 * Zentralisierte Basisklasse für alle Mesh-Agenten innerhalb von Sovereign Studio.
 * Regelt die Event-Bus-Kommunikation, das standardisierte Logging und Lifecycle-Management.
 */
export class BaseAgent {
  constructor(agentId, config = {}) {
    if (!agentId) {
      throw new Error("BaseAgent: agentId ist zwingend erforderlich.");
    }
    this.agentId = agentId;
    this.config = config;
    this.eventBus = EventBus;
    this.subscriptions = new Map();
    
    this.log(`Agent ${this.agentId} initialisiert.`);
  }

  /**
   * Sendet ein Event an den globalen Event-Bus.
   * @param {string} event - Name des Events
   * @param {Object} payload - Dateninhalt
   */
  emit(event, payload = {}) {
    const message = {
      sender: this.agentId,
      timestamp: Date.now(),
      data: payload
    };
    this.eventBus.emit(event, message);
  }

  /**
   * Abonniert ein Event und registriert den Handler für automatische Bereinigung.
   * @param {string} event - Name des Events
   * @param {Function} handler - Callback-Funktion
   */
  subscribe(event, handler) {
    const wrappedHandler = (payload) => handler(payload);
    this.eventBus.on(event, wrappedHandler);
    this.subscriptions.set(event, wrappedHandler);
  }

  /**
   * Standardisiertes Logging für die Sovereign Studio Umgebung.
   * @param {string} message - Log-Nachricht
   * @param {string} level - Log-Level (info, warn, error, debug)
   */
  log(message, level = 'info') {
    const timestamp = new Date().toISOString();
    const formattedMessage = `[${timestamp}] [${this.agentId}] [${level.toUpperCase()}]: ${message}`;

    switch (level) {
      case 'error':
        console.error(formattedMessage);
        break;
      case 'warn':
        console.warn(formattedMessage);
        break;
      case 'debug':
        if (this.config.debug) console.debug(formattedMessage);
        break;
      default:
        console.log(formattedMessage);
    }
  }

  /**
   * Lifecycle-Methode: Initialisierung des Agenten.
   * Sollte in Subklassen überschrieben werden.
   */
  async setup() {
    this.log('Setup-Phase gestartet.');
  }

  /**
   * Bereinigt alle Subscriptions und Ressourcen des Agenten.
   */
  terminate() {
    this.log('Wird beendet. Bereinige Subscriptions...');
    this.subscriptions.forEach((handler, event) => {
      this.eventBus.off(event, handler);
    });
    this.subscriptions.clear();
  }

  /**
   * Wrapper für Fehlerbehandlung innerhalb der Agenten-Logik.
   * @param {Error|string} error 
   */
  handleError(error) {
    const errorMessage = error instanceof Error ? error.message : error;
    this.log(errorMessage, 'error');
    this.emit('agent:error', { agent: this.agentId, error: errorMessage });
  }
}