import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkbenchEmptyState } from './WorkbenchEmptyState';

const baseProps = {
  wishText: '',
  hasConversationContent: false,
  effectiveRepoReady: true,
  githubWriteAllowed: true,
  agentReady: true,
  localRepoLoading: false,
  chatResponseBusy: false,
  isPublishing: false,
  onPresetActionSelect: vi.fn(),
};

describe('WorkbenchEmptyState', () => {
  it('renders onboarding only for a genuinely empty conversation', () => {
    render(<WorkbenchEmptyState {...baseProps} />);
    expect(screen.getByText('Was möchtest du tun?')).toBeDefined();
  });

  it('does not replace restored conversation content after reload', () => {
    const { container } = render(
      <WorkbenchEmptyState {...baseProps} hasConversationContent />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('does not render onboarding while the composer already contains a draft', () => {
    const { container } = render(
      <WorkbenchEmptyState {...baseProps} wishText="bestehender Entwurf" />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
