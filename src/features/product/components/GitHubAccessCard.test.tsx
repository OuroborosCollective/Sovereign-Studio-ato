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

  it('keeps manual credential recovery available during an active OAuth validation', () => {
    const onProvideToken = vi.fn();
    render(
      <GitHubAccessCard
        snapshot={startGitHubAccessValidation('ghp_****test')}
        onProvideToken={onProvideToken}
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'GitHub-Zugang schließen' })).toBeNull();
    expect(screen.getByText('GitHub-Zugang wird geprüft')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Zugang eingeben' }));
    expect(screen.getByLabelText(/GitHub Token/i)).toBeDefined();
    expect(onProvideToken).not.toHaveBeenCalled();
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

    const accessCard = screen.getByTestId('github-access-card');
    expect(accessCard).toHaveAttribute('role', 'group');
    fireEvent.click(screen.getByText('Zugang eingeben'));
    const dialog = screen.getByRole('dialog', { name: 'GitHub-Zugang' });
    expect(dialog).toBeDefined();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Abbrechen' }));
    expect(screen.getByLabelText(/GitHub Token/i)).toBeDefined();
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByLabelText(/GitHub Token/i)).toBeNull();
    expect(onProvideToken).not.toHaveBeenCalled();
  });

  it('renders status icon with aria-hidden, focus rings, contextual titles, and describes validation error', () => {
    const onProvideToken = vi.fn();
    const { container } = render(
      <GitHubAccessCard
        snapshot={createGitHubAccessSnapshot()}
        onProvideToken={onProvideToken}
        onDismiss={vi.fn()}
      />,
    );

    const icon = container.querySelector('[aria-hidden="true"]');
    expect(icon).toBeInTheDocument();

    const openBtn = screen.getByRole('button', { name: 'Zugang eingeben' });
    expect(openBtn).toHaveAttribute('title', 'GitHub Personal Access Token eingeben');
    expect(openBtn).toHaveClass('focus-visible:ring-2');

    const dismissBtn = screen.getByRole('button', { name: 'GitHub-Zugang schließen' });
    expect(dismissBtn).toHaveAttribute('title', 'GitHub-Zugang schließen');
    expect(dismissBtn).toHaveClass('focus-visible:ring-2');

    // Open modal
    fireEvent.click(openBtn);

    const input = screen.getByLabelText(/GitHub Token/i);
    expect(input).toHaveAttribute('aria-invalid', 'false');
    expect(input).toHaveAttribute('aria-describedby', 'github-pat-help');
    expect(input).toHaveClass('focus-visible:ring-2');

    const submitBtn = screen.getByRole('button', { name: 'Übernehmen' });
    expect(submitBtn).toBeDisabled();
    expect(submitBtn).toHaveAttribute('title', 'Bitte geben Sie zuerst ein gültiges GitHub-Token ein');
    expect(submitBtn).toHaveClass('focus-visible:ring-2');

    const cancelBtn = screen.getByRole('button', { name: 'Abbrechen' });
    expect(cancelBtn).toHaveAttribute('title', 'Eingabe abbrechen und Dialog schließen');
    expect(cancelBtn).toHaveClass('focus-visible:ring-2');

    // Enter invalid token
    fireEvent.change(input, { target: { value: 'invalid-token' } });
    expect(submitBtn).not.toBeDisabled();
    expect(submitBtn).toHaveAttribute('title', 'GitHub-Token bestätigen und Zugang einrichten');

    fireEvent.click(submitBtn);

    // Validation error should appear and be described
    const errorMsg = screen.getByRole('alert');
    expect(errorMsg).toHaveTextContent(/Ungültiges Token-Format/i);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAttribute('aria-describedby', 'github-pat-error github-pat-help');
  });
});
