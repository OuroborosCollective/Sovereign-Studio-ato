import { render, screen } from '@testing-library/react';
import React from 'react';
import { describe, expect, it } from 'vitest';
import { AdminAnalyticsPanel, AdminUsageStats } from './AdminAnalyticsPanel';

describe('AdminAnalyticsPanel', () => {
  it('does not render when isAdmin is false', () => {
    const { container } = render(<AdminAnalyticsPanel isAdmin={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('correctly calculates totals in a single pass when usageStats are provided', () => {
    const usageStats: AdminUsageStats[] = [
      {
        modelId: 'gpt-4o',
        modelName: 'GPT-4o',
        promptTokens: 1000,
        completionTokens: 500,
        totalTokens: 1500,
        requestCount: 10,
        estimatedCost: 0.015,
      },
      {
        modelId: 'claude-3-5-sonnet',
        modelName: 'Claude 3.5 Sonnet',
        promptTokens: 2000,
        completionTokens: 1000,
        totalTokens: 3000,
        requestCount: 20,
        estimatedCost: 0.035,
      },
    ];

    render(<AdminAnalyticsPanel isAdmin={true} usageStats={usageStats} />);

    // Total cost = €0.050
    expect(screen.getByText('€0.050')).toBeInTheDocument();
    // Total tokens = 4500 (4.5K)
    expect(screen.getByText('4.5K')).toBeInTheDocument();
    // Total requests = 30
    expect(screen.getByText('30')).toBeInTheDocument();
  });
});
