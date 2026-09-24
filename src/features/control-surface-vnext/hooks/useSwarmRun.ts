import { useMutation } from '@tanstack/react-query';
import { useSovereignAdapter } from '../adapter/context';
import type { AgentMode } from '../types/domain';
export interface SingleAgentRunParams { prompt?: string; objective?: string; toolchains?: string[]; toolchainId?: string; activeSkillIds?: string[]; agentMode?: AgentMode; }
export function useSingleAgentRun() {
  const adapter = useSovereignAdapter();
  return useMutation({
    mutationFn: (params: SingleAgentRunParams) => {
      const prompt = params.prompt || params.objective || '';
      const toolchains = params.toolchains || (params.toolchainId ? [params.toolchainId] : []);
      if ((params.agentMode ?? 'single') !== 'single') {
        throw new Error('vNext command surface is single-agent only.');
      }
      return adapter.runSingleAgent(prompt, toolchains, params.activeSkillIds ?? []);
    },
  });
}
