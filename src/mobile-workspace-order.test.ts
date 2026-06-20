import { beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMobileWorkspace } from './mobile-workspace-order';

describe('mobile workspace order', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('places the active workspace directly below the coach and moves controls underneath', () => {
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

    expect(order).toEqual(['title', 'coach', 'active', 'automation', 'nav', 'more']);
    expect(document.querySelector('.active')?.getAttribute('data-sovereign-active-workspace')).toBe('true');
  });

  it('does not treat navigation or automation controls as active workspace', () => {
    document.body.innerHTML = `
      <div id="root">
        <div class="min-h-screen">
          <h1>Sovereign Canvas Tool</h1>
          <section id="sovereign-mobile-coach"><div>Sovereign Bot</div></section>
          <section class="automation"><h2>Automation Mode</h2><select><option>Manual</option></select></section>
          <div class="nav"><button>Repo</button><button>Builder</button><button>Files</button><button>Diff</button></div>
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

    expect(order).toEqual(['title', 'coach', 'automation', 'nav']);
  });
});
