import { describe, expect, it, vi } from 'vitest';
import { refreshOmniRouteAndReload } from './useAdminApi';

describe('refreshOmniRouteAndReload', () => {
  it('always requests typed runtime readback after a rejected double-canary', async () => {
    const refresh = vi.fn().mockRejectedValue(new Error('omniroute_canary_http_401'));
    const reload = vi.fn();

    await expect(refreshOmniRouteAndReload(refresh, reload)).rejects.toThrow(
      'omniroute_canary_http_401',
    );

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('reads back after a successful double-canary too', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const reload = vi.fn();

    await expect(refreshOmniRouteAndReload(refresh, reload)).resolves.toBeUndefined();

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
