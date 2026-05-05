import { AgentOrchestrator } from './AgentOrchestrator.js';
import { GhostPilot } from '../core/GhostPilot.js';
import { GeminiProvider } from '../ai/GeminiProvider.js';
import { logger } from '../utils/logger.js';
import { config } from '../config/mesh.config.js';

/**
 * MeshRunner
 * Zentraler Bootstrapper für das Sovereign Studio Mesh-System.
 * Orchestriert die Initialisierung von Gemini-Agenten und steuert den autonomen Ghost-Pilot Workflow.
 */
export class MeshRunner {
  constructor() {
    this.orchestrator = null;
    this.gemini = null;
    this.active = false;
    this.cycleInterval = config.cycleInterval || 10000;
  }

  /**
   * Initialisiert die KI-Provider und lädt die Agenten-Struktur.
   */
  async initialize() {
    try {
      logger.info('MeshRunner: Initializing Sovereign Mesh...');
      
      this.gemini = new GeminiProvider({
        apiKey: process.env.GEMINI_API_KEY,
        model: config.defaultModel || 'gemini-1.5-pro'
      });

      this.orchestrator = new AgentOrchestrator(this.gemini);
      await this.orchestrator.bootstrapAgents();

      logger.info('MeshRunner: Agents loaded and ready.');
    } catch (error) {
      logger.error('MeshRunner Initialization Failed:', error);
      throw error;
    }
  }

  /**
   * Startet den autonomen Build-to-Deploy Cycle.
   */
  async start() {
    if (this.active) return;
    this.active = true;

    logger.info('MeshRunner: Starting Autonomous Cycle (Ghost-Pilot)...');

    const executionLoop = async () => {
      if (!this.active) return;

      try {
        await GhostPilot.runAutonomousCycle(this.orchestrator);
      } catch (error) {
        logger.error('MeshRunner: Cycle Error', error);
      }

      // Rekursiver Aufruf für kontinuierliche Evolution
      setTimeout(executionLoop, this.cycleInterval);
    };

    executionLoop();
  }

  /**
   * Stoppt den Mesh-Runner kontrolliert.
   */
  stop() {
    logger.warn('MeshRunner: Shutting down mesh operations...');
    this.active = false;
  }

  /**
   * Verarbeitet externe Trigger oder Webhook-Events für das Repository-Management.
   */
  async handleTrigger(payload) {
    if (!this.orchestrator) await this.initialize();
    return await this.orchestrator.dispatchTask(payload);
  }
}

// Singleton Instanz für den Prozess-Start
const runner = new MeshRunner();

if (process.env.AUTO_START_MESH === 'true') {
  runner.initialize()
    .then(() => runner.start())
    .catch(err => {
      logger.error('Fatal Mesh Start Failure:', err);
      process.exit(1);
    });
}

export default runner;