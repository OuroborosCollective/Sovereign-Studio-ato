import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { DraftPrCard } from './DraftPrCard';

describe('DraftPrCard', () => {
  it('renders draft PR card only when the parent supplies a URL-backed result', () => {
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={['src/index.ts', 'src/App.tsx']}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />,
    );

    expect(screen.getByTestId('draft-pr-card')).toBeTruthy();
    expect(screen.getByText('Draft PR ready')).toBeTruthy();
  });

  it('shows changed files count', () => {
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={['file1.ts', 'file2.ts', 'file3.ts']}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />,
    );

    expect(screen.getByText(/3 geänderte Datei/i)).toBeTruthy();
  });

  it('calls onOpenBrowser when Open button clicked', () => {
    const onOpenBrowser = vi.fn();
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        onOpenBrowser={onOpenBrowser}
        onDiscussInChat={() => {}}
      />,
    );

    const openBtn = screen.getByRole('button', { name: 'Im Browser öffnen' });
    expect(openBtn).toHaveAttribute('title', 'Draft PR auf GitHub im Browser öffnen');
    expect(openBtn).not.toHaveAttribute('aria-label');
    expect(openBtn).toHaveClass('focus-visible:ring-2');
    fireEvent.click(openBtn);
    expect(onOpenBrowser).toHaveBeenCalledTimes(1);
  });

  it('calls onDiscussInChat when Discuss button clicked without auto-sending', () => {
    const onDiscussInChat = vi.fn();
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        onOpenBrowser={() => {}}
        onDiscussInChat={onDiscussInChat}
      />,
    );

    const discussBtn = screen.getByRole('button', { name: 'Im Chat besprechen' });
    expect(discussBtn).toHaveAttribute('title', 'Diesen Draft PR im Chat besprechen');
    expect(discussBtn).not.toHaveAttribute('aria-label');
    expect(discussBtn).toHaveClass('focus-visible:ring-2');
    fireEvent.click(discussBtn);
    expect(onDiscussInChat).toHaveBeenCalledTimes(1);
  });

  it('renders with empty changedFiles', () => {
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />,
    );

    expect(screen.getByText('Keine Dateien geändert')).toBeTruthy();
  });

  it('shows PR number from URL', () => {
    render(
      <DraftPrCard
        url="https://github.com/myowner/myrepo/pull/42"
        changedFiles={['README.md']}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />,
    );

    expect(screen.getByText(/PR #42/i)).toBeTruthy();
  });

  it('defaults build badge to unknown when no run data exists', () => {
    const { container } = render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />,
    );

    const badge = screen.getByRole('status', { name: /Buildstatus: Build unbekannt/i });
    expect(badge).toBeTruthy();
    expect(badge).toHaveAttribute('data-testid', 'draft-pr-build-badge');
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent('📝');
    expect(screen.getByText('Build unbekannt')).toBeTruthy();
    expect(screen.getByText(/kein grüner Status wird erfunden/i)).toBeTruthy();
  });

  it('shows successful build status only when supplied by runtime', () => {
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        buildStatus={{
          state: 'success',
          label: 'Build erfolgreich',
          detail: 'GitHub Run meldet success.',
          runUrl: 'https://github.com/owner/repo/actions/runs/999',
        }}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />,
    );

    expect(screen.getByText('Build erfolgreich')).toBeTruthy();
    const runLink = screen.getByRole('link', { name: 'Run öffnen' });
    expect(runLink).toHaveAttribute('href', 'https://github.com/owner/repo/actions/runs/999');
    expect(runLink).toHaveAttribute('title', 'GitHub Workflow Run in neuem Tab öffnen');
    expect(runLink).toHaveClass('focus-visible:ring-2');
  });

  it('shows failure, running and pending build states without percentages', () => {
    const { rerender } = render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        buildStatus={{ state: 'failure', label: 'Build fehlgeschlagen', detail: 'GitHub Run Conclusion: failure.' }}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />,
    );
    expect(screen.getByText('Build fehlgeschlagen')).toBeTruthy();

    rerender(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        buildStatus={{ state: 'running', label: 'Build läuft', detail: 'GitHub Run Status: in_progress.' }}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />,
    );
    expect(screen.getByText('Build läuft')).toBeTruthy();

    rerender(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        buildStatus={{ state: 'pending', label: 'Build wartet', detail: 'GitHub Run wartet.' }}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />,
    );
    expect(screen.getByText('Build wartet')).toBeTruthy();
    expect(screen.queryByText('%')).toBeNull();
  });
});
