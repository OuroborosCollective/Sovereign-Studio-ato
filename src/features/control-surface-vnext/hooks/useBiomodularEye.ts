import { useState, useEffect } from 'react';
import type { JobPhase } from '../types/domain';

export type OcularState = 'DORMANT' | 'AWAKENING' | 'EXECUTING' | 'AWAITING_INPUT' | 'VERIFIED';

export function useBiomodularEye(jobPhase: JobPhase | undefined, isTyping: boolean) {
  const [ocularState, setOcularState] = useState<OcularState>('DORMANT');

  useEffect(() => {
    if (jobPhase === 'IDLE' || !jobPhase) {
      setOcularState(isTyping ? 'AWAKENING' : 'DORMANT');
    } else if (jobPhase === 'AWAITING_OWNER_INPUT') {
      setOcularState('AWAITING_INPUT');
    } else if (jobPhase === 'COMPLETED') {
      setOcularState('VERIFIED');
    } else if (['DISPATCHING', 'PROVISIONING', 'EXECUTING', 'FINALIZING', 'READY_TO_PUBLISH'].includes(jobPhase)) {
      setOcularState('EXECUTING');
    } else {
      setOcularState('DORMANT');
    }
  }, [jobPhase, isTyping]);

  return ocularState;
}
