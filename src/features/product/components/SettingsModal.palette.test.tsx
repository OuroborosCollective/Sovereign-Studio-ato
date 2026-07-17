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
});
