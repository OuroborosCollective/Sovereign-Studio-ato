import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSovereignAdapter } from '../adapter/context';

const TERMINAL = new Set(['AWAITING_OWNER_INPUT', 'BLOCKED', 'READY_TO_PUBLISH', 'COMPLETED', 'FAILED', 'CANCELLED']);

export function useSovereignJob(jobId: string | null) {
  const adapter = useSovereignAdapter();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['sovereign-vnext-job', jobId],
    queryFn: () => {
      if (!jobId) throw new Error('No run ID');
      return adapter.getJob(jobId);
    },
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const phase = query.state.data?.phase;
      if (phase && TERMINAL.has(phase)) return 15000;
      return query.state.error ? 3000 : 1500;
    },
    refetchOnReconnect: true,
    refetchOnMount: 'always',
  });
  const abortMutation = useMutation({
    mutationKey: ['sovereign-vnext-abort', jobId],
    mutationFn: () => {
      if (!jobId) throw new Error('No run ID');
      return adapter.abortJob(jobId);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sovereign-vnext-job', jobId] });
    },
  });
  const prepareMutation = useMutation({
    mutationFn: () => {
      if (!jobId) throw new Error('No run ID');
      return adapter.prepareDraftPr(jobId);
    },
  });
  const publishMutation = useMutation({
    mutationFn: () => {
      if (!jobId) throw new Error('No run ID');
      return adapter.createDraftPr(jobId);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sovereign-vnext-job', jobId] }),
  });
  const job = query.data;
  return {
    job,
    isLoading: query.isLoading,
    isPolling: query.isFetching,
    error: query.error,
    abort: abortMutation.mutateAsync,
    isAborting: abortMutation.isPending,
    abortError: abortMutation.error,
    prepareDraftPr: prepareMutation.mutateAsync,
    isPreparingDraftPr: prepareMutation.isPending,
    draftPrPreparation: prepareMutation.data,
    prepareError: prepareMutation.error,
    publishDraftPr: publishMutation.mutateAsync,
    isPublishing: publishMutation.isPending,
    publishError: publishMutation.error,
    workspace: job?.workspaceState || job?.workspace,
    publication: job?.publication,
  };
}
