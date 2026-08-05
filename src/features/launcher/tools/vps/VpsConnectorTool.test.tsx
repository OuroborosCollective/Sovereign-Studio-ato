/**
 * VpsConnectorTool — Smoke Tests
 * Issue #454
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VpsConnectorTool } from './VpsConnectorTool';

// useVpsConnection mocken — kein echtes Netzwerk im Test
vi.mock('./useVpsConnection', () => ({
  useVpsConnection: () => ({
    state: { phase: 'disconnected', sessionId: null, host: '', username: '', error: null },
    connect: vi.fn(),
    disconnect: vi.fn(),
    execCommand: vi.fn(),
    getTree: vi.fn().mockResolvedValue([]),
  }),
}));

const noop = () => {};

describe('VpsConnectorTool', () => {
  it('zeigt VpsConnectionForm im disconnected-Zustand', () => {
    render(<VpsConnectorTool onClose={noop} onMinimize={noop} />);
    expect(screen.getByText(/SSH Verbinden/i)).toBeTruthy();
  });

  it('rendert ohne Crash', () => {
    const { container } = render(<VpsConnectorTool onClose={noop} onMinimize={noop} />);
    expect(container.firstChild).toBeTruthy();
  });
});

describe('VpsConnectionForm', () => {
  it('zeigt alle Pflichtfelder', () => {
    render(<VpsConnectorTool onClose={noop} onMinimize={noop} />);
    expect(screen.getByPlaceholderText(/192\.168/i)).toBeTruthy();
    expect(screen.getByPlaceholderText(/root oder ubuntu/i)).toBeTruthy();
  });
});

describe('VpsFileTree Accessibility', () => {
  it('renders directory and file nodes with correct aria-label, title, and aria-expanded attributes', async () => {
    const { VpsFileTree } = await import('./VpsFileTree');
    const mockGetTree = vi.fn().mockResolvedValue([
      { name: 'src', type: 'directory' },
      { name: 'README.md', type: 'file' },
    ]);
    const mockOnSelect = vi.fn();

    render(<VpsFileTree getTree={mockGetTree} onSelectFile={mockOnSelect} />);

    const dirButton = await screen.findByRole('button', { name: 'Verzeichnis öffnen: src' });
    expect(dirButton).toHaveAttribute('aria-expanded', 'false');
    expect(dirButton).toHaveAttribute('title', 'Verzeichnis öffnen: /src');

    const fileButton = await screen.findByRole('button', { name: 'Datei öffnen: README.md' });
    expect(fileButton).not.toHaveAttribute('aria-expanded');
    expect(fileButton).toHaveAttribute('title', 'Datei öffnen: /README.md');
  });
});
