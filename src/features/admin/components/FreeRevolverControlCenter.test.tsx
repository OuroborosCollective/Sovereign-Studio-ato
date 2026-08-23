import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { FreeRevolverControlCenter } from './FreeRevolverControlCenter';
import type { UseAdminFreeRevolverProvidersResult } from '../hooks/useAdminApi';

const sourceId = '0609e75c-8c48-59db-80a4-3155b823205b';

function apiFixture(): UseAdminFreeRevolverProvidersResult {
  return {
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
        sourceType: 'external-free-provider',
        providerSurfaceKind: 'omniroute-auto',
        lifecycle: 'active',
        canonicalAction: 'omniroute-refresh',
        label: 'OmniRoute Auto',
        apiBase: 'http://omniroute:20128/v1',
        modelsUrl: null,
        authMode: 'none',
        keyHint: 'ohne Key',
        status: 'degraded',
        lastHttpStatus: 401,
        lastErrorCode: 'omniroute_canary_http_401',
        lastDiscoveredAt: null,
        lastCheckedAt: null,
        enabled: true,
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
    omniRoute: {
      ok: false,
      routeSource: 'omniroute',
      routeId: 'sovereign-omniroute-auto',
      modelId: 'sovereign-omniroute:auto',
      apiBase: 'http://omniroute:20128/v1',
      disabled: true,
      activationState: 'blocked',
      blocker: 'omniroute_canary_http_401',
      confirmationCount: 0,
      receiptSha256: null,
      sourceRevision: 'a'.repeat(40),
      imageDigest: `sha256:${'b'.repeat(64)}`,
      freeLlmApiChanged: false,
      rawProviderResponsesReturned: false,
    },
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
        accountWideQuotaScope: 'openrouter-free',
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
    refreshOmniRoute: vi.fn().mockResolvedValue(undefined),
  };
}

describe('FreeRevolverControlCenter typed provider action boundary', () => {
  it('uses the dedicated OmniRoute refresh and never the generic discovery action', async () => {
    const api = apiFixture();
    const user = userEvent.setup();

    render(
      <FreeRevolverControlCenter
        api={api}
        eligibilityEvidenceTtlHours={24}
      />,
    );

    expect(screen.getByTestId('provider-surface-openrouter-free')).toBeVisible();
    expect(screen.getByTestId('provider-surface-omniroute')).toBeVisible();
    expect(screen.getByTestId('provider-surface-freellm-api')).toBeVisible();

    await user.click(screen.getByTestId('provider-action-omniroute-refresh'));

    expect(api.refreshOmniRoute).toHaveBeenCalledTimes(1);
    expect(api.discover).not.toHaveBeenCalled();
  });

  it('counts accepted OmniRoute runtime truth in ready, verified, and blocked totals', () => {
    const blockedApi = apiFixture();
    const { rerender } = render(
      <FreeRevolverControlCenter
        api={blockedApi}
        eligibilityEvidenceTtlHours={24}
      />,
    );

    expect(within(screen.getByTestId('free-revolver-total-ready')).getByText('0')).toBeVisible();
    expect(within(screen.getByTestId('free-revolver-total-verified')).getByText('0')).toBeVisible();
    expect(within(screen.getByTestId('free-revolver-total-blocked')).getByText('1')).toBeVisible();

    const readyApi = apiFixture();
    readyApi.omniRoute = {
      ...readyApi.omniRoute!,
      ok: true,
      disabled: false,
      activationState: 'ready',
      blocker: null,
      confirmationCount: 2,
      receiptSha256: 'c'.repeat(64),
    };
    rerender(
      <FreeRevolverControlCenter
        api={readyApi}
        eligibilityEvidenceTtlHours={24}
      />,
    );

    expect(within(screen.getByTestId('free-revolver-total-ready')).getByText('1')).toBeVisible();
    expect(within(screen.getByTestId('free-revolver-total-verified')).getByText('1')).toBeVisible();
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
