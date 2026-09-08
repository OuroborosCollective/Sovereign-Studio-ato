import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FreeRevolverControlCenter } from './FreeRevolverControlCenter';
import type { UseAdminFreeRevolverProvidersResult } from '../hooks/useAdminApi';

const sourceId = '0609e75c-8c48-59db-80a4-3155b823205b';

function apiFixture(): UseAdminFreeRevolverProvidersResult {
  return {
    minimumReadyRoutes: 5,
    providers: [
      {
        id: 'freellmapi-source',
        sourceType: 'freellmapi-direct',
        providerSurfaceKind: 'free-revolver',
        lifecycle: 'active',
        canonicalAction: 'revolver-discover',
        label: 'FreeLLM API',
        apiBase: 'http://freellmapi:3001/v1',
        modelsUrl: 'http://freellmapi:3001/v1/models',
        authMode: 'managed-bearer',
        keyHint: 'owner-managed',
        status: 'healthy',
        lastHttpStatus: 200,
        lastErrorCode: null,
        lastDiscoveredAt: null,
        lastCheckedAt: null,
        enabled: true,
        ownerRequestId: null,
        models: [],
      },
      {
        id: sourceId,
        sourceType: 'omniroute',
        providerSurfaceKind: 'retired-reference',
        lifecycle: 'historical',
        canonicalAction: 'none',
        label: 'OmniRoute (retired)',
        apiBase: 'http://omniroute:20128/v1',
        modelsUrl: null,
        authMode: 'none',
        keyHint: null,
        status: 'disabled',
        lastHttpStatus: null,
        lastErrorCode: 'omniroute_retired_owner_simplification',
        lastDiscoveredAt: null,
        lastCheckedAt: null,
        enabled: false,
        ownerRequestId: null,
        models: [],
      },
      {
        id: 'freellmpool-source',
        sourceType: 'freellmpool-private',
        providerSurfaceKind: 'retired-reference',
        lifecycle: 'historical',
        canonicalAction: 'none',
        label: 'FreeLLMPool 0.11.4 · privater Docker',
        apiBase: 'http://freellmpool:8080/v1',
        modelsUrl: null,
        authMode: 'managed-bearer',
        keyHint: null,
        status: 'disabled',
        lastHttpStatus: null,
        lastErrorCode: 'freellmpool_replaced_by_omniroute',
        lastDiscoveredAt: null,
        lastCheckedAt: null,
        enabled: false,
        ownerRequestId: null,
        models: [],
      },
    ],
    openRouterPaid: {
      status: 'ready',
      deploymentStatus: 'ready',
      routeId: 'openrouter-root',
      transport: 'openrouter',
      keyStored: true,
      keyHint: '…paid',
      selectableModels: 1,
      lastCanaryRequestId: null,
      lastCanaryAt: null,
      lastErrorCode: null,
      secretValuesReturned: false,
    },
    openRouterFree: {
      ok: true,
      status: 'OPENROUTER_FREE_RUNTIME_STATUS',
      freeExecutionKey: {},
      managementKey: {},
      route: {},
      managementTableAvailable: true,
      managementTableBlocker: null,
      routingPolicy: {
        priority: 5,
        providerModel: 'openrouter/free',
        fallbackAfterQuota: 'freellm',
        paidFallbackAllowed: false,
        accountWideQuotaScope: 'openrouter:account:free-models',
      },
      runtimeIdentity: {},
      secretValuesReturned: false,
    },
    loading: false,
    error: null,
    reload: vi.fn(),
    createAndDiscover: vi.fn(),
    autoConfigureKey: vi.fn(),
    renewAndDiscover: vi.fn(),
    discover: vi.fn(),
    recheck: vi.fn(),
    toggle: vi.fn(),
  };
}

describe('FreeRevolverControlCenter typed provider action boundary', () => {
  it('shows FreeLLMAPI and OpenRouter while OmniRoute is historical-only', () => {
    render(
      <FreeRevolverControlCenter
        api={apiFixture()}
        eligibilityEvidenceTtlHours={24}
      />,
    );

    expect(screen.getByTestId('provider-surface-openrouter-free')).toBeVisible();
    expect(screen.getByTestId('provider-surface-freellm-api')).toBeVisible();
    expect(screen.queryByTestId('provider-surface-omniroute')).toBeNull();
    const retired = screen.getByTestId('provider-surface-retired-reference');
    expect(within(retired).getByText('OmniRoute (retired)')).toBeVisible();
    expect(within(retired).queryAllByRole('button')).toHaveLength(0);
  });

  it('does not count retired provider references as ready, verified, or blocked', () => {
    render(
      <FreeRevolverControlCenter
        api={apiFixture()}
        eligibilityEvidenceTtlHours={24}
      />,
    );

    expect(within(screen.getByTestId('free-revolver-total-ready')).getByText('0')).toBeVisible();
    expect(within(screen.getByTestId('free-revolver-minimum-ready')).getByText('0/5')).toBeVisible();
    expect(within(screen.getByTestId('free-revolver-total-verified')).getByText('0')).toBeVisible();
    expect(within(screen.getByTestId('free-revolver-total-blocked')).getByText('0')).toBeVisible();
  });

  it('retains the migrated FreeLLMPool entry only as non-executable history', () => {
    render(
      <FreeRevolverControlCenter
        api={apiFixture()}
        eligibilityEvidenceTtlHours={24}
      />,
    );

    const retired = screen.getByTestId('provider-surface-retired-freellmpool');
    expect(within(retired).getByText('Historische Referenz')).toBeVisible();
    expect(within(retired).queryAllByRole('button')).toHaveLength(0);
    expect(within(retired).getByText(/Keine Discovery, kein Healthcheck/)).toBeVisible();
  });
});
