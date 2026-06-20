import { beforeEach, describe, expect, it, vi } from 'vitest';
import { installMobileWorkspaceOrder, orderMobileWorkspace } from './mobile-workspace-order';

function setViewport(width: number): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('767px') ? width <= 767 : false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('mobile workspace order', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
    setViewport(390);
  });

  it('places the active workspace directly below the installed coach without moving the nav/coach pair', () => {
    document.body.innerHTML = `
      <div id="root">
        <div class="min-h-screen">
          <h1>Sovereign Canvas Tool</h1>
          <div class="nav"><button>Repo</button><button>Builder</button><button>Files</button><button>Diff</button></div>
          <section id="sovereign-mobile-coach"><div>Sovereign Bot</div></section>
          <section class="automation"><h2>Automation Mode</h2><select><option>Full Auto Draft PR</option></select></section>
          <section class="active"><h2>Sovereign Action Builder</h2><textarea></textarea></section>
          <section class="more"><h2>Mehr Bereiche: Logs, Speicher, Checks...</h2></section>
        </div>
      </div>
    `;

    expect(orderMobileWorkspace()).toBe(true);

    const shell = document.querySelector('#root > div')!;
    const order = Array.from(shell.children).map((child) => {
      if (child.tagName.toLowerCase() === 'h1') return 'title';
      if (child.id === 'sovereign-mobile-coach') return 'coach';
      if (child.classList.contains('active')) return 'active';
      if (child.classList.contains('automation')) return 'automation';
      if (child.classList.contains('nav')) return 'nav';
      if (child.classList.contains('more')) return 'more';
      return 'other';
    });

    expect(order).toEqual(['title', 'nav', 'coach', 'active', 'automation', 'more']);
    expect(document.querySelector('.active')?.getAttribute('data-sovereign-active-workspace')).toBe('true');
  });

  it('does not treat navigation or automation controls as active workspace', () => {
    document.body.innerHTML = `
      <div id="root">
        <div class="min-h-screen">
          <h1>Sovereign Canvas Tool</h1>
          <div class="nav"><button>Repo</button><button>Builder</button><button>Files</button><button>Diff</button></div>
          <section id="sovereign-mobile-coach"><div>Sovereign Bot</div></section>
          <section class="automation"><h2>Automation Mode</h2><select><option>Manual</option></select></section>
        </div>
      </div>
    `;

    expect(orderMobileWorkspace()).toBe(true);

    const shell = document.querySelector('#root > div')!;
    const order = Array.from(shell.children).map((child) => {
      if (child.tagName.toLowerCase() === 'h1') return 'title';
      if (child.id === 'sovereign-mobile-coach') return 'coach';
      if (child.classList.contains('automation')) return 'automation';
      if (child.classList.contains('nav')) return 'nav';
      return 'other';
    });

    expect(order).toEqual(['title', 'nav', 'coach', 'automation']);
  });

  it('does not reorder desktop layouts', () => {
    setViewport(1024);
    document.body.innerHTML = `
      <div id="root">
        <div class="min-h-screen">
          <h1>Sovereign Canvas Tool</h1>
          <section class="active"><h2>Sovereign Action Builder</h2></section>
          <div class="nav"><button>Repo</button><button>Builder</button><button>Files</button><button>Diff</button></div>
          <section id="sovereign-mobile-coach"><div>Sovereign Bot</div></section>
        </div>
      </div>
    `;

    expect(orderMobileWorkspace()).toBe(false);

    const shell = document.querySelector('#root > div')!;
    expect(Array.from(shell.children).map((child) => child.className || child.id || child.tagName.toLowerCase())).toEqual([
      '',
      'active',
      'nav',
      'sovereign-mobile-coach',
    ]);
  });

  it('does not observe the active workspace marker it writes', () => {
    const observe = vi.spyOn(MutationObserver.prototype, 'observe');
    document.body.innerHTML = '<div id="root"><div class="min-h-screen"><h1>Sovereign Canvas Tool</h1></div></div>';

    installMobileWorkspaceOrder();

    expect(observe).toHaveBeenCalledWith(document.body, expect.objectContaining({
      attributeFilter: ['class', 'hidden', 'style', 'data-role'],
    }));
  });
});
