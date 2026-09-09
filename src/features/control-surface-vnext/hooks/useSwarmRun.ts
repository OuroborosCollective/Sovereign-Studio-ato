import { useMutation } from '@tanstack/react-query';
import { useSovereignAdapter } from '../adapter/context';
export interface SwarmRunParams { prompt?: string; objective?: string; toolchains?: string[]; toolchainId?: string; activeSkillIds?: string[]; }
export function useSwarmRun() {
  const adapter = useSovereignAdapter();
  return useMutation({
    mutationFn: (params: SwarmRunParams) => {
      const prompt = params.prompt || params.objective || '';
      const toolchains = params.toolchains || (params.toolchainId ? [params.toolchainId] : []);
      return adapter.runSwarm(prompt, toolchains, params.activeSkillIds ?? []);
    },
  });
}
