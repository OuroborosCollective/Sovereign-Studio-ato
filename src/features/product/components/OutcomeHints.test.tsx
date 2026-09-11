// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';
import { OutcomeHints } from './OutcomeHints';

describe('OutcomeHints Security & Rendering', () => {
  afterEach(cleanup);

  it('renders valid HTTPS URL with target="_blank" and rel="noopener noreferrer"', () => {
    render(
      <OutcomeHints
        hints={[
          {
            kind: 'draft-pr',
            text: 'Draft PR bereit · Öffnen',
            href: 'https://github.com/example/repo/pull/42',
          },
        ]}
      />
    );

    const link = screen.getByRole('link', { name: 'Draft PR bereit · Öffnen' });
    expect(link).toBeDefined();
    expect(link.getAttribute('href')).toBe('https://github.com/example/repo/pull/42');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('sanitizes unsafe javascript: URL and renders as plain text without a link element', () => {
    render(
      <OutcomeHints
        hints={[
          {
            kind: 'draft-pr',
            text: 'Unsafe Link Test',
            href: 'javascript:alert(document.cookie)',
          },
        ]}
      />
    );

    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Unsafe Link Test')).toBeDefined();
  });

  it('sanitizes unsafe http: URL and renders as plain text without a link element', () => {
    render(
      <OutcomeHints
        hints={[
          {
            kind: 'draft-pr',
            text: 'Insecure HTTP Link',
            href: 'http://insecure-website.com',
          },
        ]}
      />
    );

    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Insecure HTTP Link')).toBeDefined();
  });

  it('renders hints without href as plain text', () => {
    render(
      <OutcomeHints
        hints={[
          {
            kind: 'runtime',
            text: 'Sovereign Agent ID: 12345',
          },
        ]}
      />
    );

    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Sovereign Agent ID: 12345')).toBeDefined();
  });
});
