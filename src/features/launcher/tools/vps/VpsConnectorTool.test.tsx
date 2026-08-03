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
  it('zeigt alle Pflichtfelder und korrekte Accessibility-Verknüpfungen', () => {
    render(<VpsConnectorTool onClose={noop} onMinimize={noop} />);

    // Test labels and input association
    expect(screen.getByLabelText(/HOST \/ IP/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/PORT/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/BENUTZERNAME/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/PASSWORT/i)).toBeInTheDocument();

    // Test password button has correct attributes
    const pwdBtn = screen.getByRole('button', { name: 'Passwort' });
    expect(pwdBtn).toHaveAttribute('aria-pressed', 'true');
    expect(pwdBtn).toHaveAttribute('title', 'Authentifizierungsmethode Passwort auswählen');

    // Test SSH-Key button has correct attributes
    const keyBtn = screen.getByRole('button', { name: 'SSH-Key' });
    expect(keyBtn).toHaveAttribute('aria-pressed', 'false');
    expect(keyBtn).toHaveAttribute('title', 'Authentifizierungsmethode SSH-Key auswählen');
  });
});
