import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GitHubAccessCard } from './GitHubAccessCard';
import { createGitHubAccessSnapshot, startGitHubAccessValidation } from '../runtime/githubAccessRuntime';

describe('GitHubAccessCard', () => {
  it('allows a manually opened missing-access surface to close without changing access state', () => {
    const onDismiss = vi.fn();
    render(
      <GitHubAccessCard
        snapshot={createGitHubAccessSnapshot()}
        onProvideToken={vi.fn()}
        onDismiss={onDismiss}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'GitHub-Zugang schließen' }));
    expect(onDismiss).toHaveBeenCalledOnce();
    expect(screen.getByText('GitHub-Zugang fehlt')).toBeDefined();
  });

  it('keeps an active validation visible instead of offering a fake dismiss', () => {
    render(
      <GitHubAccessCard
        snapshot={startGitHubAccessValidation('ghp_****test')}
        onProvideToken={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'GitHub-Zugang schließen' })).toBeNull();
    expect(screen.getByText('GitHub-Zugang wird geprüft')).toBeDefined();
  });

  it('closes the secure token modal with Escape and does not submit anything', () => {
    const onProvideToken = vi.fn();
    render(
      <GitHubAccessCard
        snapshot={createGitHubAccessSnapshot()}
        onProvideToken={onProvideToken}
        onDismiss={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText('Zugang eingeben'));
    expect(screen.getByLabelText(/GitHub Token/i)).toBeDefined();
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByLabelText(/GitHub Token/i)).toBeNull();
    expect(onProvideToken).not.toHaveBeenCalled();
  });
});
