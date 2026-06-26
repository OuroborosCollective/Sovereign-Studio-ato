import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { SOVEREIGN_PRODUCT_TEMPLATE } from './features/product/runtime/sovereignProductTemplate';

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8');
}

describe('main app entry', () => {
  it('renders the current Sovereign composition wrapper, not the legacy ProductMagic shell', () => {
    const main = readSource('./main.tsx');
    const wrapper = readSource('./SovereignAppWrapper.tsx');

    expect(main).toContain("import App from './SovereignAppWrapper'");
    expect(main).toContain('<App />');
    expect(wrapper).toContain("import App from './App'");
    expect(wrapper).toContain('<App />');
    expect(main).not.toContain("import ProductMagicApp from './ProductMagicApp'");
    expect(main).not.toContain('<ProductMagicApp />');
    expect(wrapper).not.toContain('ProductMagicApp');
  });

  it('derives tabs from the Product Template as single source of truth', () => {
    const app = readSource('./App.tsx');

    // App should import the Product Template
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE');
    // App should use startTab from template
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE.startTab');
    // All visible tabs from the template should be available
    const visibleTabs = SOVEREIGN_PRODUCT_TEMPLATE.tabs.filter((t) => t.userVisible);
    expect(visibleTabs.length).toBeGreaterThan(0);
    // Check that the template is used to derive tabs
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE.tabs');
  });

  it('keeps visible container app navigation and runtime surfaces available via Product Template', () => {
    const app = readSource('./App.tsx');

    // All visible tabs from the Product Template should be handled in app rendering
    const visibleTabs = SOVEREIGN_PRODUCT_TEMPLATE.tabs.filter((t) => t.userVisible);
    for (const tab of visibleTabs) {
      expect(app).toContain(`'${tab.id}'`);
    }
  });

  it('wires the runtime auto-view router into the live app shell', () => {
    const app = readSource('./App.tsx');

    expect(app).toContain('decideSovereignAutoView');
    expect(app).toContain("view:auto-switch");
    expect(app).toContain('setActiveTab(decision.tab)');
    expect(app).toContain('workflowStatus: workflowReport?.status');
  });

  it('keeps the release shell styling contract in the Android web build', () => {
    const css = readSource('./index.css');

    expect(css).toContain('--surface-1');
    expect(css).toContain('--accent-2');
    expect(css).toContain('Release shell');
    expect(css).toContain('Container runtime');
    expect(css).toContain('Android phones, foldables and tablets only');
  });
});
