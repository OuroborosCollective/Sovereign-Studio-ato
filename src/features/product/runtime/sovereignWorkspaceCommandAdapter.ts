import {
  normalizeSovereignWorkspaceCommandDetail,
  type SovereignWorkspaceCommandDetail,
} from './sovereignWorkspaceCommand';

export function normalizeSovereignWorkspaceCommandAdapterInput(value: unknown): SovereignWorkspaceCommandDetail | null {
  return normalizeSovereignWorkspaceCommandDetail(value);
}
