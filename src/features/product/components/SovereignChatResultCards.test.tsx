import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SovereignChatResultCards } from './SovereignChatResultCards';

describe('SovereignChatResultCards', () => {
  it('renders nothing when there are no cards', () => {
    const { container } = render(<SovereignChatResultCards cards={[]} />);

    expect(container.firstChild).toBeNull();
  });

  it('renders calm cards for runtime id and draft pr', () => {
    render(<SovereignChatResultCards cards={[
      {
        kind: 'runtime-id',
        title: 'Echte OpenHands Runtime',
        message: 'Küken folgt echter Runtime-ID conv_real_123.',
      },
      {
        kind: 'draft-pr',
        title: 'Draft PR bereit',
        message: 'Bitte prüfen, nicht automatisch mergen.',
        actionLabel: 'Draft PR öffnen',
        actionUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1',
      },
    ]} />);

    expect(screen.getByTestId('sovereign-chat-result-cards')).toBeDefined();
    expect(screen.getByText('Echte OpenHands Runtime')).toBeDefined();
    expect(screen.getByText('Draft PR bereit')).toBeDefined();
    expect(screen.getByRole('link', { name: 'Draft PR öffnen' })).toHaveAttribute('href', 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1');
  });

  it('renders changed files without opening log spam', () => {
    render(<SovereignChatResultCards cards={[
      {
        kind: 'changed-files',
        title: 'Geänderte Dateien',
        message: '2 Datei(en) von OpenHands gemeldet.',
        items: ['src/App.tsx', 'README.md'],
      },
    ]} />);

    expect(screen.getByText('src/App.tsx')).toBeDefined();
    expect(screen.getByText('README.md')).toBeDefined();
  });
});
