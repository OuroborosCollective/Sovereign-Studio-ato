#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text("utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), "utf-8")


# App: the stream state/effect is already created by the primary patch. Replace
# the one remaining JSX prop that still referenced the deleted PNG frame state.
replace_once(
    "src/App.tsx",
    "          desktopFrame={desktopFrame?.jobId === canonicalAgentJob.jobId ? desktopFrame : null}\n",
    "          desktopStream={desktopStream?.jobId === canonicalAgentJob.jobId ? desktopStream : null}\n",
)

stream_type_with_job = """  desktopStream?: {
    readonly jobId: string;
    readonly url: string;
    readonly frameHash: string;
    readonly observedAt: number;
  } | null;
"""
stream_type_without_job = """  readonly desktopStream?: {
    readonly url: string;
    readonly frameHash: string;
    readonly observedAt: number;
  } | null;
"""
replacement_with_job = """  desktopStream?: {
    readonly jobId: string;
    readonly url: string;
    readonly activationId: string;
    readonly sessionBindingHash: string;
    readonly expiresAtEpoch: number;
  } | null;
"""
replacement_without_job = """  readonly desktopStream?: {
    readonly url: string;
    readonly activationId: string;
    readonly sessionBindingHash: string;
    readonly expiresAtEpoch: number;
  } | null;
"""

# The primary patch deliberately performs a symbol rename. Complete the type
# migration explicitly so downstream monitor props are stream descriptors, not
# stale PNG-frame observations.
replace_once(
    "src/features/product/containers/BuilderContainer.tsx",
    stream_type_with_job,
    replacement_with_job,
)
replace_once(
    "src/features/product/components/AgentEventStream.tsx",
    stream_type_without_job,
    replacement_without_job,
)
replace_once(
    "src/features/product/components/LiveWorkspaceMonitor.tsx",
    stream_type_without_job,
    replacement_without_job,
)

# There are two identical status fallbacks in BuilderContainer. The first one
# handles `status` and returns. TypeScript correctly narrows `offlineIntent`
# afterwards, making the second comparison impossible. Remove only that
# duplicate unreachable block; do not broaden the intent union.
duplicate_status = """      if (offlineIntent === 'status') {
        appendRuntimeNotice(buildExecutorStatusAnswer({
            agentState: agentWorkSnapshot.state,
            agentStatus: scopedAgentJob?.status,
            changedFiles: scopedAgentJob?.changedFiles?.length ?? 0,
            draftPrUrl: scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl ?? null,
            blockerReason: agentWorkSnapshot.blockerReason,
          }));
        return;
      }

"""
replace_once(
    "src/features/product/containers/BuilderContainer.tsx",
    duplicate_status,
    "",
)

print("BYTEBOT_LIVE_DESKTOP_FRONTEND_TYPE_FIX_APPLIED")
