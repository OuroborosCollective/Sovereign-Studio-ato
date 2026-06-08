export interface ApprovalSyncRequest {
  repoUrl: string;
  workflowCode: string;
  manifestJson: string;
  blueprint: string;
}

export interface ApprovalSyncSuccess {
  ok: true;
  branchName: string;
  pullRequestUrl: string;
  commitSha?: string;
}

export interface ApprovalSyncFailure {
  ok: false;
  code: string;
  message: string;
}

export type ApprovalSyncResponse = ApprovalSyncSuccess | ApprovalSyncFailure;

export class ApprovalSyncError extends Error {
  constructor(
    message: string,
    public readonly code: string = "APPROVAL_SYNC_FAILED"
  ) {
    super(message);
    this.name = "ApprovalSyncError";
  }
}

export async function syncApproval(request: ApprovalSyncRequest): Promise<ApprovalSyncSuccess> {
  const endpoint = import.meta.env.VITE_APPROVAL_SYNC_URL;

  if (!endpoint) {
    throw new ApprovalSyncError(
      "Approval Sync ist nicht konfiguriert. VITE_APPROVAL_SYNC_URL fehlt.",
      "APPROVAL_SYNC_URL_MISSING"
    );
  }

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(request),
  });

  let payload: ApprovalSyncResponse;

  try {
    payload = (await response.json()) as ApprovalSyncResponse;
  } catch {
    throw new ApprovalSyncError(
      "Approval Sync lieferte keine lesbare JSON-Antwort.",
      "APPROVAL_SYNC_BAD_JSON"
    );
  }

  if (!response.ok || !payload.ok) {
    const failure = payload as ApprovalSyncFailure;
    throw new ApprovalSyncError(
      payload.ok ? "Approval Sync fehlgeschlagen." : failure.message,
      payload.ok ? "APPROVAL_SYNC_HTTP_ERROR" : failure.code
    );
  }

  if (!payload.pullRequestUrl || !payload.branchName) {
    throw new ApprovalSyncError(
      "Approval Sync erfolgreich gemeldet, aber Ziel-Link fehlt.",
      "APPROVAL_SYNC_TARGET_MISSING"
    );
  }

  return payload;
}