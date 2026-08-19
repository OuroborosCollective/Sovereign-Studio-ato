/**
 * ChatMarkdown full-subset tests (Issue #1567, finding E1)
 * Verifies headings, lists, horizontal rules, pipe tables and italic emphasis.
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { ChatMarkdown } from './ChatMarkdown';

describe('ChatMarkdown full markdown subset', () => {
  describe('headings', () => {
    it('renders ## as h2 without raw hashes', () => {
      const { container } = render(<ChatMarkdown content={'## Titel'} />);
      const h = container.querySelector('h2');
      expect(h).toBeTruthy();
      expect(h?.textContent).toBe('Titel');
      expect(container.textContent).not.toContain('##');
    });

    it('renders # through ###### at the correct levels', () => {
      const content = ['# a', '## b', '### c', '#### d', '##### e', '###### f'].join('\n');
      const { container } = render(<ChatMarkdown content={content} />);
      for (let level = 1; level <= 6; level += 1) {
        expect(container.querySelector(`h${level}`)).toBeTruthy();
      }
    });
  });

  describe('horizontal rules', () => {
    it.each(['---', '***', '___'])('renders %s as hr', (marker) => {
      const { container } = render(<ChatMarkdown content={`oben\n${marker}\nunten`} />);
      expect(container.querySelector('hr')).toBeTruthy();
      expect(container.textContent).not.toContain(marker);
    });
  });

  describe('lists', () => {
    it('renders unordered list items', () => {
      const { container } = render(<ChatMarkdown content={'- eins\n- zwei'} />);
      const items = container.querySelectorAll('ul li');
      expect(items).toHaveLength(2);
      expect(items[0].textContent).toBe('eins');
      expect(items[1].textContent).toBe('zwei');
    });

    it('renders ordered list items', () => {
      const { container } = render(<ChatMarkdown content={'1. eins\n2. zwei'} />);
      const items = container.querySelectorAll('ol li');
      expect(items).toHaveLength(2);
    });
  });

  describe('pipe tables', () => {
    it('renders a table with header and rows', () => {
      const content = '| Name | Wert |\n| --- | --- |\n| a | 1 |\n| b | 2 |';
      const { container } = render(<ChatMarkdown content={content} />);
      const table = container.querySelector('table');
      expect(table).toBeTruthy();
      const headers = container.querySelectorAll('th');
      expect(headers).toHaveLength(2);
      expect(headers[0].textContent).toBe('Name');
      const cells = container.querySelectorAll('td');
      expect(cells).toHaveLength(4);
      expect(cells[0].textContent).toBe('a');
    });

    it('does not render a table without a separator row (streaming safety)', () => {
      const { container } = render(<ChatMarkdown content={'| Name | Wert |\n| a | 1 |'} />);
      expect(container.querySelector('table')).toBeNull();
    });

    it('does not render an unfinished pipe row as a table', () => {
      const { container } = render(<ChatMarkdown content={'| Name | Wer'} />);
      expect(container.querySelector('table')).toBeNull();
    });
  });

  describe('italic emphasis', () => {
    it('renders _italic_ as em', () => {
      const { container } = render(<ChatMarkdown content={'das ist _wichtig_ hier'} />);
      const em = container.querySelector('em');
      expect(em).toBeTruthy();
      expect(em?.textContent).toBe('wichtig');
    });

    it('renders *italic* as em', () => {
      const { container } = render(<ChatMarkdown content={'das ist *wichtig* hier'} />);
      const em = container.querySelector('em');
      expect(em).toBeTruthy();
      expect(em?.textContent).toBe('wichtig');
    });
  });

  describe('regressions / robustness', () => {
    it('still renders bold inside headings', () => {
      const { container } = render(<ChatMarkdown content={'## **Fett** Titel'} />);
      const h = container.querySelector('h2');
      expect(h?.querySelector('strong')?.textContent).toBe('Fett');
    });

    it('does not break on an unclosed code fence (streaming)', () => {
      const { container } = render(<ChatMarkdown content={'```ts\nconst x = 1;'} />);
      expect(container.textContent).toContain('const x = 1;');
    });

    it('does not render raw markdown for mixed content', () => {
      const content = '## Plan\n\n- Schritt 1\n- Schritt 2\n\n---\n\n| A | B |\n| --- | --- |\n| 1 | 2 |';
      const { container } = render(<ChatMarkdown content={content} />);
      expect(container.textContent).not.toContain('##');
      expect(container.textContent).not.toContain('| ---');
    });
  });
});
