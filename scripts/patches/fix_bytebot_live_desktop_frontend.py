#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text("utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), "utf-8")


def replace_once_in_span(path: str, span_start: str, span_end: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text("utf-8")
    start = text.find(span_start)
    if start < 0:
        raise SystemExit(f"{path}: missing span start {span_start!r}")
    end = text.find(span_end, start)
    if end < 0:
        raise SystemExit(f"{path}: missing span end {span_end!r}")
    segment = text[start:end]
    count = segment.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one scoped anchor, found {count}: {old[:120]!r}")
    segment = segment.replace(old, new, 1)
    target.write_text(text[:start] + segment + text[end:], "utf-8")


# App: the stream state/effect is already created by the primary patch. Replace
# the one remaining JSX prop that still referenced the deleted PNG frame state.
replace_once(
    "src/App.tsx",
    "          desktopFrame={desktopFrame?.jobId === canonicalAgentJob.jobId ? desktopFrame : null}\n",
    "          desktopStream={desktopStream?.jobId === canonicalAgentJob.jobId ? desktopStream : null}\n",
)

# The app-shell contract must move with the product invariant: continuous stream
# is required; the old primary PNG polling call is explicitly forbidden.
replace_once(
    "src/appShellContract.test.ts",
    "      'getDesktopFrame(jobId)',\n    ]);\n    expect(app).not.toContain('data-layout=\"chat-only-live-entry\"');\n",
    "      'getDesktopStreamTicket(jobId)',\n    ]);\n    expect(app).not.toContain('getDesktopFrame(jobId)');\n    expect(app).not.toContain('data-layout=\"chat-only-live-entry\"');\n",
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

# The BuilderContainer type is the public contract consumed by App.tsx. Scope
# this replacement to that exported interface so another lookalike block can
# never satisfy the patch while leaving the real component contract stale.
replace_once_in_span(
    "src/features/product/containers/BuilderContainer.tsx",
    "export interface BuilderContainerProps {\n",
    "\n}\n\n// Local types",
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

# Fail closed on the exact exported prop contract. This is deliberately stronger
# than a repository-wide grep because App.tsx is type-checked against this span.
builder = Path("src/features/product/containers/BuilderContainer.tsx").read_text("utf-8")
start = builder.index("export interface BuilderContainerProps {\n")
end = builder.index("\n}\n\n// Local types", start)
props = builder[start:end]
for required in ("desktopStream?: {", "readonly activationId: string;", "readonly sessionBindingHash: string;", "readonly expiresAtEpoch: number;"):
    if required not in props:
        raise SystemExit(f"BuilderContainerProps missing required stream contract: {required}")
if "desktopFrame?:" in props or "readonly frameHash: string;" in props:
    raise SystemExit("BuilderContainerProps still contains stale PNG frame contract")

shell_contract = Path("src/appShellContract.test.ts").read_text("utf-8")
if "'getDesktopStreamTicket(jobId)'" not in shell_contract:
    raise SystemExit("app shell contract does not require the live stream ticket")
if "expect(app).not.toContain('getDesktopFrame(jobId)');" not in shell_contract:
    raise SystemExit("app shell contract does not forbid primary PNG polling")

print("BYTEBOT_LIVE_DESKTOP_FRONTEND_TYPE_FIX_APPLIED")
