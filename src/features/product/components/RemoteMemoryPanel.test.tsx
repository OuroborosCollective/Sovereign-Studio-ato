import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RemoteMemoryPanel } from './RemoteMemoryPanel';
import {
  EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT,
  createExternalMemorySyncConfig,
  type ExternalMemoryDeleteResult,
} from '../runtime/externalMemorySync';
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

function cleanupResult(): ExternalMemoryDeleteResult {
  return {
    status: 'synced',
    deleted: true,
    validation: { valid: true, errors: [], warnings: [], summary: 'ok' },
    response: { success: true, deleted: true, deletedItems: 2, retainedSharedItems: 8, summary: 'contributor records removed' },
    summary: 'contributor records removed',
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

  it('requires scope checkbox and exact confirmation text before contributor cleanup', () => {
    const onCleanupContributor = vi.fn();
    const onCleanupConfirmationTextChange = vi.fn();
    const onCleanupScopeConfirmedChange = vi.fn();

    const { rerender } = render(
      <RemoteMemoryPanel
        config={baseConfig()}
        syncResult={null}
        healthResult={null}
        monitoringResult={null}
        previewResult={null}
        searchResult={null}
        updatesResult={null}
        intakeResult={null}
        isBusy={false}
        cleanupConfirmationText=""
        cleanupScopeConfirmed={false}
        onChange={vi.fn()}
        onCleanupConfirmationTextChange={onCleanupConfirmationTextChange}
        onCleanupScopeConfirmedChange={onCleanupScopeConfirmedChange}
        onHealth={vi.fn()}
        onMonitoring={vi.fn()}
        onSync={vi.fn()}
        onSearch={vi.fn()}
        onPullUpdates={vi.fn()}
        onCleanupContributor={onCleanupContributor}
      />,
    );

    const button = screen.getByRole('button', { name: /Contributor Remote Memory bereinigen/i });
    expect(button).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/Nur meine contributor-submissions/i));
    expect(onCleanupScopeConfirmedChange).toHaveBeenCalledWith(true);

    fireEvent.change(screen.getByPlaceholderText(EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT), {
      target: { value: EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT },
    });
    expect(onCleanupConfirmationTextChange).toHaveBeenCalledWith(EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT);

    rerender(
      <RemoteMemoryPanel
        config={baseConfig()}
        syncResult={null}
        healthResult={null}
        monitoringResult={null}
        previewResult={null}
        searchResult={null}
        updatesResult={null}
        intakeResult={null}
        isBusy={false}
        cleanupConfirmationText={EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT}
        cleanupScopeConfirmed={true}
        onChange={vi.fn()}
        onCleanupConfirmationTextChange={onCleanupConfirmationTextChange}
        onCleanupScopeConfirmedChange={onCleanupScopeConfirmedChange}
        onHealth={vi.fn()}
        onMonitoring={vi.fn()}
        onSync={vi.fn()}
        onSearch={vi.fn()}
        onPullUpdates={vi.fn()}
        onCleanupContributor={onCleanupContributor}
      />,
    );

    const readyButton = screen.getByRole('button', { name: /Contributor Remote Memory bereinigen/i });
    expect(readyButton).not.toBeDisabled();
    fireEvent.click(readyButton);
    expect(onCleanupContributor).toHaveBeenCalledOnce();
  });

  it('renders contributor cleanup result', () => {
    render(
      <RemoteMemoryPanel
        config={baseConfig()}
        syncResult={null}
        healthResult={null}
        monitoringResult={null}
        previewResult={null}
        cleanupResult={cleanupResult()}
        searchResult={null}
        updatesResult={null}
        intakeResult={null}
        isBusy={false}
        onChange={vi.fn()}
        onHealth={vi.fn()}
        onMonitoring={vi.fn()}
        onSync={vi.fn()}
        onSearch={vi.fn()}
        onPullUpdates={vi.fn()}
      />,
    );

    expect(screen.getByText(/Bereinigen: contributor records removed/i)).toBeDefined();
  });
});
