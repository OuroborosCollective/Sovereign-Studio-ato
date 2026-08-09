// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MobileNavigation } from './MobileNavigation';

describe('MobileNavigation Accessibility and Interaction', () => {
  const defaultProps = {
    activeTab: 'explorer' as const,
    setActiveTab: vi.fn(),
  };

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders correct navigation with proper ARIA attributes', () => {
    render(<MobileNavigation {...defaultProps} />);

    // Nav container should have aria-label
    const nav = screen.getByRole('navigation', { name: 'Mobile Navigation' });
    expect(nav).toBeInTheDocument();

    // Active button has active state, title, aria-current, and aria-label
    const explorerBtn = screen.getByRole('button', { name: /Aktiviert: Planung – Planung und Workspace-Übersicht anzeigen/i });
    expect(explorerBtn).toBeInTheDocument();
    expect(explorerBtn).toHaveAttribute('aria-current', 'page');
    expect(explorerBtn).toHaveAttribute('title', 'Aktiviert: Planung – Planung und Workspace-Übersicht anzeigen');

    // Inactive buttons have normal descriptions, titles, but no aria-current
    const editorBtn = screen.getByRole('button', { name: /Code anzeigen – Code-Editor und Quelldateien anzeigen/i });
    expect(editorBtn).toBeInTheDocument();
    expect(editorBtn).not.toHaveAttribute('aria-current');
    expect(editorBtn).toHaveAttribute('title', 'Code anzeigen – Code-Editor und Quelldateien anzeigen');

    const chatBtn = screen.getByRole('button', { name: /Log anzeigen – Arbeitsprotokoll und Agenten-Ereignisse anzeigen/i });
    expect(chatBtn).toBeInTheDocument();
    expect(chatBtn).not.toHaveAttribute('aria-current');
    expect(chatBtn).toHaveAttribute('title', 'Log anzeigen – Arbeitsprotokoll und Agenten-Ereignisse anzeigen');
  });

  it('triggers setActiveTab callback when clicked', () => {
    const setActiveTabMock = vi.fn();
    render(<MobileNavigation {...defaultProps} setActiveTab={setActiveTabMock} />);

    const editorBtn = screen.getByRole('button', { name: /Code anzeigen – Code-Editor und Quelldateien anzeigen/i });
    fireEvent.click(editorBtn);

    expect(setActiveTabMock).toHaveBeenCalledTimes(1);
    expect(setActiveTabMock).toHaveBeenCalledWith('editor');
  });
});
