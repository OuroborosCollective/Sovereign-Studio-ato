/**
 * DraftPrCard tests
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { DraftPrCard } from './DraftPrCard';

describe('DraftPrCard', () => {
  it('renders draft PR card', () => {
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={['src/index.ts', 'src/App.tsx']}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />
    );
    expect(screen.getByTestId('draft-pr-card')).toBeTruthy();
  });

  it('shows changed files count', () => {
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={['file1.ts', 'file2.ts', 'file3.ts']}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />
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
      />
    );
    fireEvent.click(screen.getByText('Im Browser öffnen'));
    expect(onOpenBrowser).toHaveBeenCalledTimes(1);
  });

  it('calls onDiscussInChat when Discuss button clicked', () => {
    const onDiscussInChat = vi.fn();
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        onOpenBrowser={() => {}}
        onDiscussInChat={onDiscussInChat}
      />
    );
    fireEvent.click(screen.getByText('Im Chat besprechen'));
    expect(onDiscussInChat).toHaveBeenCalledTimes(1);
  });

  it('renders with empty changedFiles', () => {
    render(
      <DraftPrCard
        url="https://github.com/owner/repo/pull/123"
        changedFiles={[]}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />
    );
    expect(screen.getByText('Im Browser öffnen')).toBeTruthy();
  });

  it('shows PR number from URL', () => {
    render(
      <DraftPrCard
        url="https://github.com/myowner/myrepo/pull/42"
        changedFiles={['README.md']}
        onOpenBrowser={() => {}}
        onDiscussInChat={() => {}}
      />
    );
    expect(screen.getByText(/PR #42/i)).toBeTruthy();
  });
});
