import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RemoteMemoryPanel } from './RemoteMemoryPanel';
import { createExternalMemorySyncConfig } from '../runtime/externalMemorySync';
import type { ExternalMemorySyncPreview } from '../runtime/externalMemorySyncPreview';

function baseConfig() {
  return {
    ...createExternalMemorySyncConfig(),
    enabled: true,
    consentAccepted: true,
    gatewayUrl: 'https://memory.example.test',
    contributorId: 'install-abc',
  };
}

function preview(): ExternalMemorySyncPreview {
  return {
    valid: true,
    itemCount: 3,
    estimatedBytes: 123,
    contributorId: 'install-abc',
    workspaceId: 'Pattern',
    collectionName: 'collection',
    redaction: 'summary-only-no-source-files',
    includesRawSourceFiles: false,
    includesSessionSecret: false,
    kindCounts: { 'scan-finding': 1, 'learning-pattern': 1, 'solution-pattern': 1 },
    validation: { valid: true, errors: [], warnings: [], summary: 'ok' },
    summary: '3 sanitized items ready',
  };
}

describe('RemoteMemoryPanel', () => {
  it('renders preview button and result when provided', () => {
    const onPreview = vi.fn();
    render(
      <RemoteMemoryPanel
        config={baseConfig()}
        syncResult={null}
        healthResult={null}
        monitoringResult={null}
        previewResult={preview()}
        searchResult={null}
        updatesResult={null}
        intakeResult={null}
        isBusy={false}
        onChange={vi.fn()}
        onHealth={vi.fn()}
        onMonitoring={vi.fn()}
        onPreview={onPreview}
        onSync={vi.fn()}
        onSearch={vi.fn()}
        onPullUpdates={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Sync Preview/i }));

    expect(onPreview).toHaveBeenCalledOnce();
    expect(screen.getByText(/Preview: 3 sanitized items ready/i)).toBeDefined();
  });
});
