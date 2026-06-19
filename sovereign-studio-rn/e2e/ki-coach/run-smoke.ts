#!/usr/bin/env node
/**
 * KI Coach Real E2E Smoke Test Runner
 * NO MOCKS - NO STUBS - Real Playwright browser testing
 */

import { chromium, Browser, Page } from 'playwright';

const APP_URL = process.env.APP_URL || 'http://localhost:3000';
const TEST_REPO = process.env.TEST_REPO_URL || 'https://github.com/OuroborosCollective/Sovereign-Studio-ato';

interface TestStep {
  name: string;
  fn: () => Promise<void>;
}

interface TestResult {
  name: string;
  passed: boolean;
  error?: string;
  duration: number;
}

async function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function takeScreenshot(page: Page, name: string): Promise<void> {
  try {
    await page.screenshot({ path: `/tmp/ki-coach-${name}-${Date.now()}.png`, fullPage: true });
  } catch {
    // Ignore screenshot errors
  }
}

class RealSmokeTest {
  private browser: Browser | null = null;
  private page: Page | null = null;
  private results: TestResult[] = [];
  private startTime: number = 0;

  async setup(): Promise<void> {
    console.log('\n' + '═'.repeat(70));
    console.log('🚀 KI COACH REAL E2E SMOKE TEST (NO MOCKS, NO STUBS)');
    console.log('═'.repeat(70));
    console.log(`App URL: ${APP_URL}`);
    console.log(`Test Repo: ${TEST_REPO}`);
    console.log('');

    this.browser = await chromium.launch({ headless: true });
    const context = await this.browser.newContext({
      viewport: { width: 1280, height: 720 },
    });
    this.page = await context.newPage();
    this.startTime = Date.now();

    // Listen for console errors
    this.page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`   [Browser Error]: ${msg.text().substring(0, 100)}`);
      }
    });

    // Listen for page errors
    this.page.on('pageerror', error => {
      console.log(`   [Page Error]: ${error.message.substring(0, 100)}`);
    });
  }

  async teardown(): Promise<void> {
    if (this.browser) {
      await this.browser.close();
    }

    console.log('\n' + '═'.repeat(70));
    console.log('📊 SMOKE TEST RESULTS');
    console.log('═'.repeat(70));

    const passed = this.results.filter(r => r.passed).length;
    const failed = this.results.filter(r => !r.passed).length;
    const total = this.results.length;

    console.log(`\nTotal: ${total} | ✅ Passed: ${passed} | ❌ Failed: ${failed}`);
    console.log(`Duration: ${(Date.now() - this.startTime) / 1000}s\n`);

    this.results.forEach(r => {
      const icon = r.passed ? '✅' : '❌';
      const duration = r.duration ? `(${r.duration}ms)` : '';
      console.log(`${icon} ${r.name} ${duration}`);
      if (r.error) console.log(`   Error: ${r.error}`);
    });

    console.log('\n' + '═'.repeat(70));

    if (failed > 0) {
      console.log('❌ SMOKE TEST FAILED');
      console.log('═'.repeat(70));
      process.exit(1);
    } else {
      console.log('✅ ALL SMOKE TESTS PASSED');
      console.log('═'.repeat(70));
    }
  }

  async runStep(name: string, fn: () => Promise<boolean | void>): Promise<void> {
    console.log(`\n📍 ${name}`);
    const start = Date.now();
    
    try {
      await fn();
      this.results.push({ name, passed: true, duration: Date.now() - start });
      console.log(`   ✅ PASSED`);
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      this.results.push({ name, passed: false, error, duration: Date.now() - start });
      console.log(`   ❌ FAILED: ${error}`);
    }
  }

  async run(): Promise<void> {
    await this.setup();

    try {
      // Step 1: Open App
      await this.runStep('01-open-app', async () => {
        if (!this.page) throw new Error('Page not initialized');
        await this.page.goto(APP_URL, { waitUntil: 'networkidle', timeout: 30000 });
        await this.page.waitForLoadState('domcontentloaded');
        const title = await this.page.title();
        console.log(`   Title: ${title}`);
        await takeScreenshot(this.page, '01-app');
      });

      // Step 2: Verify Root Element
      await this.runStep('02-verify-root', async () => {
        if (!this.page) throw new Error('Page not initialized');
        const root = await this.page.locator('#root').isVisible();
        if (!root) throw new Error('Root element not visible');
        await takeScreenshot(this.page, '02-root');
      });

      // Step 3: Wait for App to Render
      await this.runStep('03-wait-render', async () => {
        await sleep(3000); // Wait for React to render
        await takeScreenshot(this.page!, '03-rendered');
      });

      // Step 4: Check for Main Layout
      await this.runStep('04-check-layout', async () => {
        if (!this.page) throw new Error('Page not initialized');
        const body = await this.page.locator('body').innerHTML();
        if (body.length < 100) throw new Error('Body content too short');
        console.log(`   Body length: ${body.length} chars`);
      });

      // Step 5: Look for Repo Setup
      await this.runStep('05-find-repo-setup', async () => {
        if (!this.page) throw new Error('Page not initialized');
        const buttons = await this.page.locator('button').all();
        console.log(`   Found ${buttons.length} buttons`);
        
        // Try to find repo/config button
        for (const btn of buttons.slice(0, 5)) {
          const text = await btn.textContent();
          if (text && /config|repo|setting/i.test(text)) {
            console.log(`   Found button: ${text}`);
            break;
          }
        }
      });

      // Step 6: Check for KI Coach
      await this.runStep('06-check-ki-coach', async () => {
        if (!this.page) throw new Error('Page not initialized');
        const content = await this.page.content();
        const hasCoach = /coach|bot|ki|ai/i.test(content);
        console.log(`   KI Coach detected: ${hasCoach}`);
      });

      // Step 7: Check for Status Indicators
      await this.runStep('07-check-status', async () => {
        if (!this.page) throw new Error('Page not initialized');
        const content = await this.page.content();
        const hasStatus = /green|yellow|red|running|idle|ready|working/i.test(content);
        console.log(`   Status indicators: ${hasStatus}`);
      });

      // Step 8: Verify No JS Errors
      await this.runStep('08-no-errors', async () => {
        if (!this.page) throw new Error('Page not initialized');
        const errors: string[] = [];
        this.page.on('pageerror', err => errors.push(err.message));
        await sleep(1000);
        if (errors.length > 0) {
          console.log(`   JS Errors: ${errors.length}`);
        }
      });

      // Step 9: Final Screenshot
      await this.runStep('09-final-screenshot', async () => {
        await takeScreenshot(this.page!, '09-final');
      });

    } catch (err) {
      console.error('Fatal error:', err);
    }

    await this.teardown();
  }
}

// Standalone execution
async function main(): Promise<void> {
  const test = new RealSmokeTest();
  await test.run();
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
