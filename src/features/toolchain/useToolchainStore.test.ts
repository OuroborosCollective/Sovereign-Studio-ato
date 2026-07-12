import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toolchainApi } from './toolchainApi';
import { useToolchainStore } from './useToolchainStore';

describe('useToolchainStore embedded universal runtime', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useToolchainStore.getState().reset();
  });

  it('auto-loads the embedded manifest beside the existing user tools', async () => {
    vi.spyOn(toolchainApi, 'getUserTools').mockResolvedValue({
      tools: [{ id: 'github_read_file', label: 'GitHub Datei lesen', write: false }],
      allowed_repos: ['ouroboroscollective/sovereign-studio-ato'],
      rules: {
        auto_load: true,
        github_read: 'after_login',
        auto_write: false,
        push_to_main: false,
        pr_mode: 'draft_only',
        confirm_required: true,
        audit_log: true,
      },
    });
    vi.spyOn(toolchainApi, 'getUniversalManifest').mockResolvedValue({
      name: 'Sovereign Universal Toolchain',
      version: '2.0.0-embedded',
      runtime: 'embedded',
      tools: [
        {
          name: 'runtime_failure_diagnose',
          description: 'Diagnose runtime evidence.',
          write_action: false,
        },
      ],
      policy: {
        autoLoad: true,
        pushToMain: false,
        draftPrOnly: true,
        confirmRequired: true,
        arbitraryShell: false,
        directProductionRunner: false,
        directGithubToken: false,
        auditEvidence: true,
      },
    });

    await useToolchainStore.getState().loadTools();

    const state = useToolchainStore.getState();
    expect(state.loaded).toBe(true);
    expect(state.universalManifest?.runtime).toBe('embedded');
    expect(state.getToolContext()).toContain('2.0.0-embedded');
    expect(state.getToolContext()).toContain('genau vier logisch benachbarte Runtime-Risiken');
    expect(state.getToolContext()).toContain('Arbitrary Shell aus Chat: gesperrt');
  });

  it('delegates predictive diagnosis without enabling a write action', async () => {
    const diagnose = vi.spyOn(toolchainApi, 'diagnoseRuntime').mockResolvedValue({
      ok: true,
      result: {
        ok: true,
        runtime: 'sovereign-universal-toolchain',
        version: '2.0.0-embedded',
        evidenceHash: 'a'.repeat(64),
        failureFamilies: [{
          code: 'typescript_contract_mismatch',
          title: 'TypeScript contract mismatch',
          severity: 'high',
          score: 3,
          checks: ['run targeted typecheck'],
        }],
        nextLogicalFailures: [1, 2, 3, 4].map(index => ({
          fromFamily: 'typescript_contract_mismatch',
          prediction: `Risk ${index}`,
          checkNext: `Check ${index}`,
        })),
        policy: { writeAction: false, pushToMain: false },
      },
    });

    const result = await useToolchainStore.getState().diagnoseRuntime(
      'Fix the TypeScript handoff',
      'TS2339 Property paymentMethods does not exist',
    );

    expect(result.nextLogicalFailures).toHaveLength(4);
    expect(diagnose).toHaveBeenCalledWith({
      mission: 'Fix the TypeScript handoff',
      evidence_text: 'TS2339 Property paymentMethods does not exist',
    });
  });
});
