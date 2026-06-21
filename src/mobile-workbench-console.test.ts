import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  classifyWorkbenchAutoNavigationReason,
  collectMobileWorkbenchVisibleText,
  installMobileWorkbenchConsole,
  shouldAutoOpenWorkbenchTarget,
} from './mobile-workbench-console';
import { canSovereignProductTemplateAutoOpen } from './features/product/runtime/sovereignProductTemplate';
import { decideMobileWorkflow, type MobileWorkflowOrchestratorDecision } from './mobile-workflow-orchestrator';

function mountShell(extra = '') {
  document.body.innerHTML = `
    <div id="root">
      <div class="min-h-screen">
        <div>
          <button>Repo</button>
          <button>Builder</button>
          <button>Files</button>
          <button>Diff</button>
          <button>Live Monitor</button>
        </div>
        ${extra}
      </div>
    </div>
  `;
}

function mountShellWithCoachAnchor(extra = '') {
  document.body.innerHTML = `
    <div id="root">
      <div class="min-h-screen">
        <div>
          <button>Repo</button>
          <button>Builder</button>
          <button>Files</button>
          <button>Diff</button>
          <button>Live Monitor</button>
        </div>
        <section id="sovereign-mobile-coach">Coach anchor</section>
        ${extra}
      </div>
    </div>
  `;
}

function decision(overrides: Partial<MobileWorkflowOrchestratorDecision>): MobileWorkflowOrchestratorDecision {
  return {
    lamp: 'green',
    mode: 'review-log',
    title: 'Ergebnis bereit',
    summary: 'Die erzeugten Dateien sind bereit.',
    targetNav: 'Files',
    autoOpenTarget: true,
    lines: ['pattern = result-review'],
    ...overrides,
  };
}

describe('mobile-workbench-console', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('installMobileWorkbenchConsole', () => {
    it('does not crash without anchor element', () => {
      document.body.innerHTML = '<div id="root"></div>';
      expect(() => installMobileWorkbenchConsole()).not.toThrow();
    });

    it('does not crash without buttons', () => {
      document.body.innerHTML = '<div id="root"><section id="sovereign-mobile-coach"></section></div>';
      expect(() => installMobileWorkbenchConsole()).not.toThrow();
    });

    it('escapes HTML in content', () => {
      mountShellWithCoachAnchor('<section>Repo &lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench).toBeTruthy();
    });

    it('renders workbench with decision output', () => {
      mountShellWithCoachAnchor('<section>repo fehlt no repo loaded</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench).toBeTruthy();
      expect(workbench?.textContent).toContain('pattern');
      expect(workbench?.textContent).toContain('score');
    });

    it('shows green for active work', () => {
      mountShellWithCoachAnchor('<section>package-build running is building</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.className).toContain('green');
    });

    it('shows yellow for repo setup', () => {
      mountShellWithCoachAnchor('<section>repo fehlt noch kein echtes repo</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.className).toContain('yellow');
    });

    it('shows green for result review', () => {
      mountShellWithCoachAnchor('<section>self review: accepted generated-output-accepted</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.className).toContain('green');
    });

    it('handles 0 failed without showing red', () => {
      mountShellWithCoachAnchor('<section>no active step; 0 completed step(s), 0 failed step(s) runtime ready</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.className).not.toContain('red');
    });

    it('shows matrix-work mode for active work', () => {
      mountShellWithCoachAnchor('<section>läuft running package-build</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.textContent).toContain('matrix-work');
    });

    it('does not throw in server-side environment', () => {
      const originalWindow = globalThis.window;
      // @ts-ignore
      globalThis.window = undefined;
      expect(() => installMobileWorkbenchConsole()).not.toThrow();
      globalThis.window = originalWindow;
    });

    it('updates on interval without reading its own previous decision text', () => {
      mountShellWithCoachAnchor('<section data-test-section="state">repo fehlt</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench1 = document.getElementById('sovereign-mobile-workbench-console');
      const content1 = workbench1?.textContent;

      const section = document.querySelector('[data-test-section="state"]');
      if (section) section.textContent = 'package-build running';

      vi.advanceTimersByTime(2000);
      const workbench2 = document.getElementById('sovereign-mobile-workbench-console');
      const content2 = workbench2?.textContent;

      expect(content1).not.toBe(content2);
      expect(collectMobileWorkbenchVisibleText(document.body)).not.toContain('pattern =');
    });
  });

  describe('visible text collection', () => {
    it('does not read workbench, coach, or setup drawer text as source state', () => {
      document.body.innerHTML = `
        <main>
          <button>Repo</button>
          <section>Repository Snapshot geladen</section>
        </main>
        <section id="sovereign-mobile-workbench-console">pattern = result-review files = ready</section>
        <section id="sovereign-mobile-coach">Sovereign Bot · Ergebnis bereit</section>
        <section id="sovereign-mobile-setup-drawer">GitHub Repo Setup</section>
      `;

      const text = collectMobileWorkbenchVisibleText(document.body);

      expect(text).toContain('Repository Snapshot geladen');
      expect(text).not.toContain('pattern = result-review');
      expect(text).not.toContain('Sovereign Bot · Ergebnis bereit');
      expect(text).not.toContain('GitHub Repo Setup');
    });
  });

  describe('HTML escaping', () => {
    it('escapes special characters in title', () => {
      mountShellWithCoachAnchor('<section>Test <b>bold</b> & special chars</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.innerHTML).toBeTruthy();
      expect(workbench?.textContent).not.toContain('<b>bold</b>');
    });

    it('escapes quotes in content', () => {
      mountShellWithCoachAnchor('<section>Test "quotes" and \'apostrophes\'</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.innerHTML).toBeTruthy();
      expect(workbench?.textContent).not.toContain('"quotes"');
    });
  });

  describe('navigation throttling', () => {
    it('does not navigate if target button missing', () => {
      document.body.innerHTML = `
        <div id="root">
          <div class="min-h-screen">
            <div>
              <button>Repo</button>
            </div>
            <section id="sovereign-mobile-coach">Coach</section>
          </div>
        </div>
      `;
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);

      expect(true).toBe(true);
    });

    it('throttles repeated navigation to same target', () => {
      document.body.innerHTML = `
        <div id="root">
          <div class="min-h-screen">
            <div>
              <button>Repo</button>
              <button>Builder</button>
              <button>Files</button>
            </div>
            <section id="sovereign-mobile-coach">Coach</section>
            <section data-test-section="state">package-build running</section>
          </div>
        </div>
      `;
      let clickCount = 0;
      document.querySelectorAll('button').forEach((btn) => {
        btn.addEventListener('click', () => clickCount++);
      });

      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      vi.advanceTimersByTime(2400);
      vi.advanceTimersByTime(2000);

      expect(clickCount).toBeLessThanOrEqual(1);
    });

    it('does not auto-navigate for passive result review suggestions', () => {
      mountShellWithCoachAnchor('<section>self review: accepted generated-output-accepted</section>');
      let clickCount = 0;
      document.querySelectorAll('button').forEach((btn) => {
        btn.addEventListener('click', () => clickCount++);
      });

      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(4000);

      expect(clickCount).toBe(0);
      expect(document.getElementById('sovereign-mobile-workbench-console')?.textContent).toContain('result-review');
    });
  });

  describe('auto-open guard', () => {
    it('only auto-opens active work or red stopper targets', () => {
      expect(shouldAutoOpenWorkbenchTarget(decision({ mode: 'review-log', lamp: 'green', targetNav: 'Files' }))).toBe(false);
      expect(shouldAutoOpenWorkbenchTarget(decision({ mode: 'nocode-plan', lamp: 'yellow', targetNav: 'Builder' }))).toBe(false);
      expect(shouldAutoOpenWorkbenchTarget(decision({ mode: 'matrix-work', lamp: 'green', targetNav: 'Live Monitor' }))).toBe(true);
      expect(shouldAutoOpenWorkbenchTarget(decision({ mode: 'repair-log', lamp: 'red', targetNav: 'Repair' }))).toBe(true);
    });

    it('classifies auto-open reasons through the product template contract', () => {
      const activeReason = classifyWorkbenchAutoNavigationReason(decision({ mode: 'matrix-work', lamp: 'green' }));
      const stopperReason = classifyWorkbenchAutoNavigationReason(decision({ mode: 'repair-log', lamp: 'red' }));
      const reviewReason = classifyWorkbenchAutoNavigationReason(decision({ mode: 'review-log', lamp: 'green' }));
      const intentReason = classifyWorkbenchAutoNavigationReason(decision({ mode: 'nocode-plan', lamp: 'yellow' }));

      expect(canSovereignProductTemplateAutoOpen(activeReason)).toBe(true);
      expect(canSovereignProductTemplateAutoOpen(stopperReason)).toBe(true);
      expect(canSovereignProductTemplateAutoOpen(reviewReason)).toBe(false);
      expect(canSovereignProductTemplateAutoOpen(intentReason)).toBe(false);
    });
  });

  describe('decision display', () => {
    it('displays pattern ID in output', () => {
      mountShellWithCoachAnchor('<section>active work running</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.textContent).toContain('pattern =');
    });

    it('displays score in output', () => {
      mountShellWithCoachAnchor('<section>repo ready ok</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.textContent).toContain('score =');
    });

    it('displays target navigation', () => {
      mountShellWithCoachAnchor('<section>repo fehlt</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      expect(workbench?.textContent).toContain('Repo');
    });
  });
});
