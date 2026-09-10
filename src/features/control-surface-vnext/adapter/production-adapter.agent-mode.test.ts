import { describe, expect, it } from 'vitest';
import { buildRunRequest } from './production-adapter';

describe('SovereignProductionAdapter agent mode contract', () => {
  it('defaults normal repository work to one FreeLLM agent', () => {
    expect(buildRunRequest('Repository: https://github.com/OuroborosCollective/Sovereign-Studio-ato\nÄndere README.md.')).toEqual({
      mission: 'Repository: https://github.com/OuroborosCollective/Sovereign-Studio-ato\nÄndere README.md.',
      mode: 'free',
      agentMode: 'single',
      intentMode: 'repository_execution',
      repositoryUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repositoryBranch: 'main',
    });
  });

  it('makes the multi-agent swarm an explicit FreeLLM opt-in', () => {
    const payload = buildRunRequest('Repository: https://github.com/OuroborosCollective/Sovereign-Studio-ato', 'swarm');
    expect(payload.mode).toBe('free');
    expect(payload.agentMode).toBe('swarm');
    expect(payload.intentMode).toBe('repository_execution');
  });

  it('keeps ordinary non-repository missions single-agent by default', () => {
    expect(buildRunRequest('Fasse den Status zusammen.')).toEqual({
      mission: 'Fasse den Status zusammen.',
      mode: 'free',
      agentMode: 'single',
      intentMode: 'auto',
    });
  });
});
