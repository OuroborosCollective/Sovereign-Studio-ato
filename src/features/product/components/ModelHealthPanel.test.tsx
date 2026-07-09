import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ModelHealthPanel } from './ModelHealthPanel';

describe('ModelHealthPanel', () => {
  it('shows an explicit empty state instead of fallback mock models', () => {
    render(<ModelHealthPanel />);

    expect(screen.getByText(/0 model\(s\)/i)).toBeDefined();
    expect(screen.getByText(/Keine LLM-Health-Daten vorhanden/i)).toBeDefined();
    expect(screen.queryByText(/Primary Bridge/i)).toBeNull();
    expect(screen.queryByText(/MLVoca/i)).toBeNull();
  });
});
