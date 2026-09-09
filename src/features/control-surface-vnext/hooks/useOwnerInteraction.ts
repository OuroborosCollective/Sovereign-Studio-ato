import { useState } from 'react';
import { useSovereignAdapter } from '../adapter/context';
import type { OwnerInteractionResponse } from '../types/domain';

export function useOwnerInteraction(jobId: string | null) {
  const adapter = useSovereignAdapter();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submitInteraction = async (response: OwnerInteractionResponse) => {
    if (!jobId) throw new Error('No active run ID to submit interaction for');
    setIsSubmitting(true);
    try {
      await adapter.resumeJob(jobId, response.interactionId, response.response);
    } finally {
      setIsSubmitting(false);
    }
  };

  return { submitInteraction, isSubmitting };
}
