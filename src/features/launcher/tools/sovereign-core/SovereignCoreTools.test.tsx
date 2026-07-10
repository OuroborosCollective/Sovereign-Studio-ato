import { render, screen, waitFor } from '@testing-library/react';
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
