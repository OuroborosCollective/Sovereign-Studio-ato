import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSovereignAdapter } from '../adapter/context';
import type { OwnerInteractionResponse } from '../types/domain';

export function useOwnerInteraction(jobId: string | null) {
  const adapter = useSovereignAdapter();
  const queryClient = useQueryClient();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submitInteraction = async (response: OwnerInteractionResponse) => {
    if (!jobId) throw new Error('No active run ID to submit interaction for');
    setIsSubmitting(true);
    try {
      await adapter.resumeJob(jobId, response.interactionId, response.response);
      await queryClient.invalidateQueries({ queryKey: ['sovereign-vnext-job', jobId] });
    } finally {
      setIsSubmitting(false);
    }
  };

  return { submitInteraction, isSubmitting };
}
