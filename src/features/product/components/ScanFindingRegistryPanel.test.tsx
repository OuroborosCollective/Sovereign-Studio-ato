// @vitest-environment jsdom

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ScanFindingRegistryPanel } from './ScanFindingRegistryPanel';
import type { ScanFindingRegistry } from '../runtime/scanFindingRegistry';

const registry: ScanFindingRegistry = {
  version: 1,
  updatedAt: 1000,
  runs: [],
  findings: [
    {
      id: 'active-1',
      category: 'security-leak',
      severity: 'critical',
      status: 'active',
      filePath: 'src/config.ts',
      title: 'Hardcoded Secret Key',
      description: 'Unmasked credential',
      fixTips: 'Move the value to a protected secret source.',
      confidence: 'content-scanned',
      source: 'test-scan',
      hits: 1,
      firstSeenAt: 1000,
      lastSeenAt: 1000,
    },
    {
      id: 'resolved-1',
      category: 'security-leak',
      severity: 'medium',
      status: 'resolved',
      filePath: 'src/api.ts',
      title: 'Resolved protocol finding',
      description: 'Previously insecure protocol',
      fixTips: 'Already resolved.',
      confidence: 'content-scanned',
      source: 'test-scan',
      hits: 1,
      firstSeenAt: 900,
      lastSeenAt: 1000,
    },
  ],
};

describe('ScanFindingRegistryPanel', () => {
  it('exposes a labelled region, semantic finding lists and keyboard-visible disclosure focus', () => {
    render(<ScanFindingRegistryPanel registry={registry} />);

    const region = screen.getByRole('region', { name: 'Scan Findings Registry' });
    expect(region).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Findings in category security-leak' }).children).toHaveLength(1);

    const resolvedSummary = screen.getByText('Resolved history · 1');
    expect(resolvedSummary).toHaveClass('focus-visible:ring-2');
    fireEvent.click(resolvedSummary);

    expect(screen.getByRole('list', { name: 'Resolved findings history' }).children).toHaveLength(1);
    expect(screen.getByLabelText('Publish gate status: needs attention')).toBeInTheDocument();
  });
});
