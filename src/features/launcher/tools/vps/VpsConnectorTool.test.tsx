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
