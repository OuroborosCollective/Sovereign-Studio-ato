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

  it('renders accessible section landmark, refresh button tooltip, and semantic list elements', () => {
    const models = [
      { id: 'm1', name: 'GPT-4o', status: 'healthy' as const, isEnabled: true, latencyMs: 120, successCount: 50, errorCount: 0 },
      { id: 'm2', name: 'Claude 3.5 Sonnet', status: 'degraded' as const, isEnabled: true, latencyMs: 2500, successCount: 40, errorCount: 2 },
    ];
    const onRefresh = () => {};

    render(<ModelHealthPanel models={models} onRefresh={onRefresh} isChecking={false} />);

    const section = screen.getByRole('region', { name: /Model Health Monitor/i });
    expect(section).toBeDefined();

    const refreshBtn = screen.getByRole('button', { name: /Refresh/i });
    expect(refreshBtn.getAttribute('title')).toBe('Model-Health Status aktualisieren');
    expect(refreshBtn.className).toContain('focus-visible:ring-2');

    const lists = screen.getAllByRole('list');
    expect(lists.length).toBeGreaterThanOrEqual(2);

    const modelItems = screen.getAllByRole('listitem');
    expect(modelItems.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/GPT-4o/i)).toBeDefined();
  });
});
