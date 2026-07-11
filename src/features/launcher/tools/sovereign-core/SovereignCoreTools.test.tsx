import { act, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  SovereignCoverageTool,
  SovereignHealthTool,
  SovereignMemoryTool,
  SovereignSettingsTool,
} from './index';
import { useSovereignToolInspectionStore } from '../../../product/runtime/sovereignToolInspectionRuntime';

const toolProps = { onClose: vi.fn(), onMinimize: vi.fn() };

beforeEach(() => {
  window.localStorage.clear();
  useSovereignToolInspectionStore.getState().resetEvidence();
  vi.restoreAllMocks();
});

describe('Sovereign core tools', () => {
  it('stores settings evidence after real browser checks', async () => {
    render(<SovereignSettingsTool {...toolProps} />);
    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.settings).toBeTruthy();
    });
    expect(screen.getByText(/Draft PR erlaubt · Auto-Merge nicht erlaubt/)).toBeInTheDocument();
  });

  it('counts memory keys but does not render their names or values', async () => {
    window.localStorage.setItem('sovereign-pattern-private-name', 'secret-content');
    render(<SovereignMemoryTool {...toolProps} />);
    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.memory?.statusLabel).toBe('1 Memory-Hinweise');
    });
    expect(screen.queryByText(/sovereign-pattern-private-name/)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret-content/)).not.toBeInTheDocument();
    expect(screen.getByText(/Schlüsselnamen und Inhalte bleiben verborgen/)).toBeInTheDocument();
  });

  it('stores scoped health evidence without claiming server or CI health', async () => {
    render(<SovereignHealthTool {...toolProps} />);
    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.health).toBeTruthy();
    });
    expect(screen.getByText(/ersetzt keine CI-, Worker- oder VPS-Prüfung/)).toBeInTheDocument();
  });

  it('updates Health and Settings evidence when browser connectivity changes', async () => {
    let online = true;
    vi.spyOn(window.navigator, 'onLine', 'get').mockImplementation(() => online);

    render(
      <>
        <SovereignHealthTool {...toolProps} />
        <SovereignSettingsTool {...toolProps} />
      </>,
    );

    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.health?.reason).not.toContain('Netzwerk offline');
      expect(useSovereignToolInspectionStore.getState().evidence.settings?.outcome).toBe('ready');
    });

    online = false;
    act(() => window.dispatchEvent(new Event('offline')));

    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.health)
        .toMatchObject({ outcome: 'warning', statusLabel: 'Client eingeschränkt' });
      expect(useSovereignToolInspectionStore.getState().evidence.health?.reason).toContain('Netzwerk offline');
      expect(useSovereignToolInspectionStore.getState().evidence.settings)
        .toMatchObject({ outcome: 'warning', statusLabel: 'Session eingeschränkt' });
    });
  });

  it('refreshes Memory evidence after a storage-state change', async () => {
    window.localStorage.setItem('sovereign-memory-one', 'hidden');
    render(<SovereignMemoryTool {...toolProps} />);

    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.memory?.statusLabel).toBe('1 Memory-Hinweise');
    });

    window.localStorage.setItem('sovereign-memory-two', 'hidden');
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'sovereign-memory-two' })));

    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.memory?.statusLabel).toBe('2 Memory-Hinweise');
    });
  });

  it('clears cancelled Coverage checking evidence on unmount', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => undefined)));
    const { unmount } = render(<SovereignCoverageTool {...toolProps} />);

    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.coverage?.outcome).toBe('checking');
    });

    unmount();
    expect(useSovereignToolInspectionStore.getState().evidence.coverage).toBeUndefined();
  });

  it('stores real coverage-map evidence from the deployment path', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ files: [{ path: 'a.ts' }, { path: 'b.ts' }] }),
    }));
    render(<SovereignCoverageTool {...toolProps} />);

    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.coverage)
        .toMatchObject({ outcome: 'ready', statusLabel: '2 Coverage-Einträge' });
    });
    expect(fetch).toHaveBeenCalledWith('/generated/test-coverage-map.json', { cache: 'no-store' });
  });

  it('stores a missing coverage result instead of showing green', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    render(<SovereignCoverageTool {...toolProps} />);

    await waitFor(() => {
      expect(useSovereignToolInspectionStore.getState().evidence.coverage)
        .toMatchObject({ outcome: 'failed', statusLabel: 'Coverage Map fehlt' });
    });
  });
});
