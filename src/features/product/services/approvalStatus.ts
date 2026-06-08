export type ApprovalStatus = 'idle' | 'ready' | 'syncing' | 'synced' | 'failed';

export interface ApprovalResult {
  status: ApprovalStatus;
  message: string;
  url?: string;
}
