import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SovereignToolLauncher } from './SovereignToolLauncher';
import { useLauncherStore } from '../../launcher/useLauncherStore';

beforeEach(() => {
  useLauncherStore.setState({ isMenuOpen: false, windows: [] });
});

describe('SovereignToolLauncher', () => {
  it('routes Files to the repo/file explorer instead of closing without effect', () => {
    const onSelect = vi.fn();
    render(<SovereignToolLauncher onSelect={onSelect} />);

    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Files' }));

    expect(onSelect).toHaveBeenCalledWith('repo');
  });

  it('opens core utility windows for direct launcher tools', () => {
    const onSelect = vi.fn();
    render(<SovereignToolLauncher onSelect={onSelect} />);

    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Settings' }));

    expect(onSelect).toHaveBeenCalledWith('settings');
    expect(useLauncherStore.getState().windows.some((entry) => entry.id === 'settings')).toBe(true);
  });
});
