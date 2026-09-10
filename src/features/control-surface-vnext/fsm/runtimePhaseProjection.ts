import type { JobPhase } from '../types/domain';

/** A linked job cannot override the persisted mission's blocker or owner boundary. */
export function projectRunAndJobPhase(runPhase: JobPhase, jobPhase: JobPhase): JobPhase {
  switch (runPhase) {
    case 'BLOCKED':
    case 'FAILED':
    case 'CANCELLED':
    case 'AWAITING_OWNER_INPUT':
      return runPhase;
    default:
      return jobPhase;
  }
}
