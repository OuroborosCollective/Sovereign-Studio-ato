import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';

const execPromise = promisify(exec);

/**
 * TesterAgent
 * Verantwortlich für die Validierung von Codeänderungen, Ausführung von Test-Suiten
 * und Verifizierung der Build-Integrität im Sovereign Studio Stack.
 */
class TesterAgent {
  constructor(config = {}) {
    this.name = 'TesterAgent';
    this.projectRoot = config.projectRoot || process.cwd();
    this.reportPath = path.join(this.projectRoot, 'reports/test-results');
  }

  /**
   * Führt die primäre Test-Pipeline aus (Vite/Vitest für Web, Gradle Check für Android).
   * @param {string} scope - 'web', 'android' oder 'all'
   */
  async runVerification(scope = 'all') {
    const results = {
      timestamp: new Date().toISOString(),
      success: true,
      tasks: []
    };

    try {
      if (scope === 'web' || scope === 'all') {
        const webResult = await this.runWebTests();
        results.tasks.push({ name: 'web-unit-tests', ...webResult });
      }

      if (scope === 'android' || scope === 'all') {
        const androidResult = await this.runAndroidLint();
        results.tasks.push({ name: 'android-lint', ...androidResult });
      }

      results.success = results.tasks.every(t => t.passed);
      await this.saveReport(results);
      return results;
    } catch (error) {
      return { success: false, error: error.message };
    }
  }

  /**
   * Führt Vitest für die Frontend-Logik aus.
   */
  async runWebTests() {
    try {
      // Nutzt die im Vite-Stack definierte Test-Umgebung
      const { stdout, stderr } = await execPromise('npm run test:run');
      return {
        passed: true,
        output: stdout,
        errors: stderr || null
      };
    } catch (error) {
      return {
        passed: false,
        output: error.stdout,
        errors: error.stderr || error.message
      };
    }
  }

  /**
   * Prüft die Gradle-Konfiguration und führt Linting für den Capacitor-Native-Layer aus.
   */
  async runAndroidLint() {
    const androidPath = path.join(this.projectRoot, 'android');
    if (!fs.existsSync(androidPath)) {
      return { passed: true, output: 'No Android project found, skipping.' };
    }

    try {
      // Ghost-Pilot Mechanismus: Validierung des Gradle-Patching-Zustands
      const { stdout } = await execPromise('cd android && ./gradlew lintDebug');
      return {
        passed: true,
        output: stdout
      };
    } catch (error) {
      return {
        passed: false,
        output: error.stdout,
        errors: error.stderr || error.message
      };
    }
  }

  /**
   * Simuliert einen Testlauf basierend auf spezifischen Dateiänderungen.
   * Wird vom Ghost-Pilot Cycle vor dem Commit aufgerufen.
   */
  async simulateChangeImpact(files) {
    console.log(`Analyzing impact for ${files.length} changed files...`);
    // Filtert Dateien nach Relevanz (z.B. .ts, .tsx, .java)
    const criticalChanges = files.filter(f => /\.(ts|tsx|java|gradle)$/.test(f));
    
    if (criticalChanges.length === 0) return { risk: 'low', action: 'proceed' };

    // Bei Änderungen an Gradle-Dateien wird ein Deep-Scan erzwungen
    const requiresNativeCheck = files.some(f => f.endsWith('.gradle'));
    return this.runVerification(requiresNativeCheck ? 'all' : 'web');
  }

  /**
   * Speichert den Testbericht für die CI/CD-Pipeline.
   */
  async saveReport(results) {
    if (!fs.existsSync(this.reportPath)) {
      fs.mkdirSync(this.reportPath, { recursive: true });
    }
    const fileName = `test-report-${Date.now()}.json`;
    await fs.promises.writeFile(
      path.join(this.reportPath, fileName),
      JSON.stringify(results, null, 2)
    );
  }
}

export default TesterAgent;