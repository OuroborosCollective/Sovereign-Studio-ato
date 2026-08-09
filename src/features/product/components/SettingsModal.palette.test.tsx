import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { SettingsModal } from './SettingsModal';
import { defaultSettings } from '../constants';

describe('SettingsModal Palette Enhancements', () => {
  const mockProps = {
    repoUrl: 'https://github.com/test/repo',
    setRepoUrl: vi.fn(),
    accessKey: 'ghp_test',
    setAccessKey: vi.fn(),
    geminiKey: 'AIza_test',
    setGeminiKey: vi.fn(),
    settings: defaultSettings,
    setSettings: vi.fn(),
    setShowSettings: vi.fn(),
    userApiKeys: {},
    setUserApiKeys: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('closes when Escape key is pressed', () => {
    render(<SettingsModal {...mockProps} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(mockProps.setShowSettings).toHaveBeenCalledWith(false);
  });

  it('toggles visibility of GitHub key', () => {
    render(<SettingsModal {...mockProps} />);
    const githubInput = screen.getByLabelText('GitHub Schreib-Key');
    const toggleButtons = screen.getAllByLabelText('Key anzeigen');
    const githubToggle = toggleButtons.find((button) => button.closest('.relative')?.contains(githubInput));

    if (!githubToggle) throw new Error('GitHub toggle not found');

    expect(githubInput).toHaveAttribute('type', 'password');

    fireEvent.click(githubToggle);
    expect(githubInput).toHaveAttribute('type', 'text');
    expect(screen.getByLabelText('Key verbergen')).toBeTruthy();

    fireEvent.click(githubToggle);
    expect(githubInput).toHaveAttribute('type', 'password');
  });

  it('toggles visibility of Gemini key', () => {
    render(<SettingsModal {...mockProps} />);
    const geminiInput = screen.getByLabelText('Gemini API-Key');
    const toggleButtons = screen.getAllByLabelText('Key anzeigen');
    const geminiToggle = toggleButtons.find((button) => button.closest('.relative')?.contains(geminiInput));

    if (!geminiToggle) throw new Error('Gemini toggle not found');

    expect(geminiInput).toHaveAttribute('type', 'password');

    fireEvent.click(geminiToggle);
    expect(geminiInput).toHaveAttribute('type', 'text');
  });

  // Obsolete: Direct API key input has been hidden/removed in favor of Sovereign Backend.
  // it('clears API key when clear button is clicked', () => { ... });

  it('renders Lucide X icon for close button', () => {
    render(<SettingsModal {...mockProps} />);
    const closeBtn = screen.getByLabelText('Schließen');
    expect(closeBtn.querySelector('svg.lucide-x')).toBeTruthy();
  });

  it('correctly associates input labels with HTML elements', () => {
    render(<SettingsModal {...mockProps} />);

    const repoLabel = screen.getByText('GitHub Repository');
    expect(repoLabel).toHaveAttribute('for', 'settings-repo-url');
    const repoInput = screen.getByLabelText('GitHub Repository URL');
    expect(repoInput).toHaveAttribute('id', 'settings-repo-url');

    const accessKeyLabel = screen.getByText('GitHub Schreib-Key (optional)');
    expect(accessKeyLabel).toHaveAttribute('for', 'settings-access-key');
    const accessKeyInput = screen.getByLabelText('GitHub Schreib-Key');
    expect(accessKeyInput).toHaveAttribute('id', 'settings-access-key');

    const packageManagerLabel = screen.getByText('Package Manager');
    expect(packageManagerLabel).toHaveAttribute('for', 'settings-package-manager');
    const packageManagerSelect = screen.getByLabelText('Package Manager auswählen');
    expect(packageManagerSelect).toHaveAttribute('id', 'settings-package-manager');

    const repoModeLabel = screen.getByText('Projektart');
    expect(repoModeLabel).toHaveAttribute('for', 'settings-repo-mode');
    const repoModeSelect = screen.getByLabelText('Projektart auswählen');
    expect(repoModeSelect).toHaveAttribute('id', 'settings-repo-mode');

    const specializationLabel = screen.getByText('Arbeitsweise');
    expect(specializationLabel).toHaveAttribute('for', 'settings-specialization');
    const specializationTextarea = screen.getByLabelText('Arbeitsweise beschreiben');
    expect(specializationTextarea).toHaveAttribute('id', 'settings-specialization');
  });

  it('renders the Speichern & Schließen button with proper title attribute', () => {
    render(<SettingsModal {...mockProps} />);
    const submitBtn = screen.getByRole('button', { name: 'Speichern & Schließen' });
    expect(submitBtn).toHaveAttribute('title', 'Einstellungen speichern und modal schließen');
  });
});
