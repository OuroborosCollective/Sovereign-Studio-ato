import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RemoteMemoryContainer } from './RemoteMemoryContainer';
import { createExternalMemorySyncConfig } from '../runtime/externalMemorySync';
import { createScanFindingRegistry } from '../runtime/scanFindingRegistry';
import { createSolutionPatternStore } from '../runtime/solutionPatternMemory';

function createLegacyBundledConfig() {
  return {
    ...createExternalMemorySyncConfig(),
    gatewayUrl: 'http://46.202.154.25:8088',
    workspaceId: 'Pattern',
    collectionName: 'sovereign_logic_patterns',
    contributorId: 'sovereign-local-install',
    allowSelfHostedHttp: true,
  };
}

describe('RemoteMemoryContainer release safety', () => {
  it('neutralizes the bundled non-local HTTP gateway before it becomes the active runtime config', async () => {
    const onConfigChange = vi.fn();
    const onTelemetry = vi.fn();

    render(
      <RemoteMemoryContainer
        config={createLegacyBundledConfig()}
        onConfigChange={onConfigChange}
        scanRegistry={createScanFindingRegistry()}
        solutionPatternStore={createSolutionPatternStore()}
        onSolutionPatternStoreChange={vi.fn()}
        mission="release safety check"
        onTelemetry={onTelemetry}
      />,
    );

    expect(screen.getByText(/bundled non-local HTTP Remote Memory gateway was disabled/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
        enabled: false,
        consentAccepted: false,
        gatewayUrl: '',
        workspaceId: 'local-workspace',
        contributorId: 'local-contributor',
        allowSelfHostedHttp: false,
      }));
    });

    expect(onTelemetry).toHaveBeenCalledWith(
      'memory',
      'warning',
      'remote-memory:unsafe-default-neutralized',
      expect.stringContaining('Bundled non-local HTTP Remote Memory gateway was disabled'),
    );
  });
});
