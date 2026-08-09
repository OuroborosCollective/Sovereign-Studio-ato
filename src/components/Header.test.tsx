// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { Header } from './Header';

describe('Header', () => {
  const defaultProps = {
    loadingTree: false,
    setShowPrivacy: vi.fn(),
    handleCleanup: vi.fn(),
    fetchRepoTree: vi.fn(),
  };

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders correctly with default props', () => {
    render(<Header {...defaultProps} />);
    expect(screen.getByText(/SOVEREIGN/i)).toBeDefined();
    expect(screen.getByText(/STUDIO/i)).toBeDefined();
    expect(screen.getByText('CANVAS AUTO-AUTH')).toBeDefined();

    const privacyBtn = screen.getByRole('button', { name: /Datenschutzerklärung anzeigen/i });
    expect(privacyBtn).toBeDefined();
    expect(privacyBtn).toHaveAttribute('title', 'Datenschutzerklärung anzeigen');

    const cleanupBtn = screen.getByRole('button', { name: /Temporäre Workspace-Dateien bereinigen/i });
    expect(cleanupBtn).toBeDefined();
    expect(cleanupBtn).toHaveAttribute('title', 'Temporäre Workspace-Dateien bereinigen');

    const refreshBtn = screen.getByRole('button', { name: /Repository-Struktur aktualisieren/i });
    expect(refreshBtn).toBeDefined();
    expect(refreshBtn).toHaveAttribute('title', 'Repository-Struktur aktualisieren');
  });

  it('calls setShowPrivacy when privacy button is clicked', () => {
    const setShowPrivacyMock = vi.fn();
    render(<Header {...defaultProps} setShowPrivacy={setShowPrivacyMock} />);

    const privacyButton = screen.getByRole('button', { name: /Datenschutzerklärung anzeigen/i });
    fireEvent.click(privacyButton);

    expect(setShowPrivacyMock).toHaveBeenCalledTimes(1);
    expect(setShowPrivacyMock).toHaveBeenCalledWith(true);
  });

  it('calls handleCleanup when cleanup button is clicked', () => {
    const handleCleanupMock = vi.fn();
    render(<Header {...defaultProps} handleCleanup={handleCleanupMock} />);

    const cleanupButton = screen.getByRole('button', { name: /Temporäre Workspace-Dateien bereinigen/i });
    fireEvent.click(cleanupButton);

    expect(handleCleanupMock).toHaveBeenCalledTimes(1);
  });

  it('calls fetchRepoTree when refresh button is clicked', () => {
    const fetchRepoTreeMock = vi.fn();
    render(<Header {...defaultProps} fetchRepoTree={fetchRepoTreeMock} />);

    const refreshButton = screen.getByRole('button', { name: /Repository-Struktur aktualisieren/i });
    fireEvent.click(refreshButton);

    expect(fetchRepoTreeMock).toHaveBeenCalledTimes(1);
  });

  it('disables refresh button and shows LADEN... when loadingTree is true', () => {
    render(<Header {...defaultProps} loadingTree={true} />);

    const refreshButton = screen.getByRole('button', { name: /Repository-Struktur wird geladen/i });
    expect(refreshButton).toBeDefined();
    expect(refreshButton).toHaveAttribute('title', 'Repository-Struktur wird geladen');
    expect((refreshButton as HTMLButtonElement).disabled).toBe(true);
  });
});
