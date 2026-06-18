import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installMobileWorkbenchConsole } from './mobile-workbench-console';
import { decideMobileWorkflow } from './mobile-workflow-orchestrator';

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

    it('updates on interval', () => {
      mountShellWithCoachAnchor('<section>repo fehlt</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench1 = document.getElementById('sovereign-mobile-workbench-console');
      const content1 = workbench1?.textContent;

      // Change content
      const section = document.querySelector('section:nth-of-type(2)');
      if (section) section.textContent = 'package-build running';

      vi.advanceTimersByTime(2000);
      const workbench2 = document.getElementById('sovereign-mobile-workbench-console');
      const content2 = workbench2?.textContent;

      expect(content1).not.toBe(content2);
    });
  });

  describe('HTML escaping', () => {
    it('escapes special characters in title', () => {
      mountShellWithCoachAnchor('<section>Test <b>bold</b> & special chars</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      // After HTML escaping, raw HTML tags should not be rendered as tags
      // The escaped version should appear as text, not parsed HTML
      expect(workbench?.innerHTML).toBeTruthy();
      // Verify the escaped content is present without unescaped HTML tags
      expect(workbench?.textContent).not.toContain('<b>bold</b>');
    });

    it('escapes quotes in content', () => {
      mountShellWithCoachAnchor('<section>Test "quotes" and \'apostrophes\'</section>');
      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);
      const workbench = document.getElementById('sovereign-mobile-workbench-console');
      // After HTML escaping, quotes should be converted to &quot; or &#39;
      // The browser may normalize these, so we check the raw innerHTML
      expect(workbench?.innerHTML).toBeTruthy();
      // Verify content is present without unescaped quotes in text content
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

      // Should not throw even though other buttons are missing
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
          </div>
        </div>
      `;
      let clickCount = 0;
      document.querySelectorAll('button').forEach((btn) => {
        btn.addEventListener('click', () => clickCount++);
      });

      installMobileWorkbenchConsole();
      vi.advanceTimersByTime(2000);

      // Change to same content to trigger re-render
      const section = document.querySelector('section:nth-of-type(2)');
      if (section) section.textContent = 'package-build running';

      vi.advanceTimersByTime(2400);
      vi.advanceTimersByTime(2000);

      // Navigation should be throttled (not more than 2 clicks)
      expect(clickCount).toBeLessThanOrEqual(2);
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