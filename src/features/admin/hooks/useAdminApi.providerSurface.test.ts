import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { adminApiClient } from '../api/adminApiClient';
import { useAdminFreeRevolverProviders } from './useAdminApi';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('admin provider surface retirement', () => {
  it('does not expose an OmniRoute action or runtime state through the admin hook', () => {
    vi.spyOn(adminApiClient, 'getLlmProviderSurfaceReadModel').mockResolvedValue({
      providers: [],
      freeRevolverMinimumReadyRoutes: 7,
      openRouterPaid: null,
      openRouterFree: null,
    });

    const { result, unmount } = renderHook(() => useAdminFreeRevolverProviders());

    expect(result.current).not.toHaveProperty('refreshOmniRoute');
    expect(result.current).not.toHaveProperty('omniRoute');
    expect(result.current).toHaveProperty('discover');
    expect(result.current).toHaveProperty('recheck');
    unmount();
  });
});
