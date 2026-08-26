from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text('utf-8')
    if text.count(old) != 1:
        raise SystemExit(f'fixup anchor mismatch: {path}: count={text.count(old)}')
    target.write_text(text.replace(old, new, 1), 'utf-8')


# The PNG state/effects are removed by the primary patch. Remove the last
# conditional prop reference and now-unused React hook import as well.
replace_once(
    'src/App.tsx',
    "import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';\n",
    "import React, { useCallback, useEffect, useMemo, useReducer, useState } from 'react';\n",
)
replace_once(
    'src/App.tsx',
    '          desktopFrame={desktopFrame?.jobId === canonicalAgentJob.jobId ? desktopFrame : null}\n',
    '',
)

# Current main contains an unreachable duplicate status fallback. The identical
# earlier status branch already appends the local status answer and returns, so
# TypeScript correctly narrows `offlineIntent` to exclude `status` here.
replace_once(
    'src/features/product/containers/BuilderContainer.tsx',
    """      if (offlineIntent === 'status') {\n        appendRuntimeNotice(buildExecutorStatusAnswer({\n            agentState: agentWorkSnapshot.state,\n            agentStatus: scopedAgentJob?.status,\n            changedFiles: scopedAgentJob?.changedFiles?.length ?? 0,\n            draftPrUrl: scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl ?? null,\n            blockerReason: agentWorkSnapshot.blockerReason,\n          }));\n        return;\n      }\n\n""",
    '',
)

# Replace the legacy PNG lifecycle regression with the new primary-monitor
# invariant: App itself must never request/carry screenshot frames. Switching
# jobs changes only the canonical job binding; the VNC stream reconnects from
# that job id inside LiveWorkspaceMonitor.
replace_once(
    'src/App.draftPrFlow.test.tsx',
    """  it('revokes and clears job A desktop evidence before job B can render', async () => {\n    const jobAHash = 'a'.repeat(64);\n    const jobBHash = 'b'.repeat(64);\n    const createObjectURL = vi.fn()\n      .mockReturnValueOnce('blob:job-a')\n      .mockReturnValueOnce('blob:job-b');\n    const revokeObjectURL = vi.fn();\n    class TestURL extends URL {}\n    Object.defineProperty(TestURL, 'createObjectURL', { configurable: true, value: createObjectURL });\n    Object.defineProperty(TestURL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });\n    vi.stubGlobal('URL', TestURL);\n\n    let resolveJobBFrame!: (frame: { blob: Blob; frameHash: string; observedAt: number }) => void;\n    const pendingJobBFrame = new Promise<{ blob: Blob; frameHash: string; observedAt: number }>((resolve) => {\n      resolveJobBFrame = resolve;\n    });\n    agent.listJobs.mockResolvedValue([snapshot({\n      jobId: 'job-a',\n      workspaceId: 'job-a',\n      runtimeId: 'job-a',\n      status: 'completed',\n    })]);\n    agent.getDesktopFrame.mockImplementation(async (jobId: string) => {\n      if (jobId === 'job-a') {\n        return { blob: new Blob(['job-a'], { type: 'image/png' }), frameHash: jobAHash, observedAt: 1 };\n      }\n      return pendingJobBFrame;\n    });\n    const jobBSnapshot = snapshot({\n      jobId: 'job-b',\n      workspaceId: 'job-b',\n      runtimeId: 'job-b',\n      status: 'running',\n    });\n    agent.startRepositoryExecution.mockResolvedValue(jobBSnapshot);\n    agent.getJob.mockResolvedValue(jobBSnapshot);\n\n    render(<Provider store={store}><App /></Provider>);\n    await waitFor(() => expect(screen.getByTestId('flow-frame-hash')).toHaveTextContent(jobAHash));\n\n    fireEvent.click(screen.getByRole('button', { name: 'Switch job' }));\n    await waitFor(() => expect(screen.getByTestId('flow-job-id')).toHaveTextContent('job-b'));\n    expect(screen.getByTestId('flow-frame-job-id')).not.toHaveTextContent('job-a');\n    await waitFor(() => expect(screen.getByTestId('flow-frame-job-id')).toHaveTextContent('none'));\n    await waitFor(() => expect(screen.getByTestId('flow-frame-hash')).toHaveTextContent('none'));\n    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:job-a'));\n    await waitFor(() => expect(agent.getDesktopFrame).toHaveBeenCalledWith('job-b'));\n    expect(createObjectURL).toHaveBeenCalledTimes(1);\n\n    await act(async () => {\n      resolveJobBFrame({\n        blob: new Blob(['job-b'], { type: 'image/png' }),\n        frameHash: jobBHash,\n        observedAt: 2,\n      });\n      await Promise.resolve();\n    });\n    await waitFor(() => expect(screen.getByTestId('flow-frame-job-id')).toHaveTextContent('job-b'));\n    await waitFor(() => expect(screen.getByTestId('flow-frame-hash')).toHaveTextContent(jobBHash));\n    expect(createObjectURL).toHaveBeenCalledTimes(2);\n  });\n""",
    """  it('never polls legacy PNG frames when switching the canonical desktop job binding', async () => {\n    agent.listJobs.mockResolvedValue([snapshot({\n      jobId: 'job-a',\n      workspaceId: 'job-a',\n      runtimeId: 'job-a',\n      status: 'completed',\n    })]);\n    const jobBSnapshot = snapshot({\n      jobId: 'job-b',\n      workspaceId: 'job-b',\n      runtimeId: 'job-b',\n      status: 'running',\n    });\n    agent.startRepositoryExecution.mockResolvedValue(jobBSnapshot);\n    agent.getJob.mockResolvedValue(jobBSnapshot);\n\n    render(<Provider store={store}><App /></Provider>);\n    await waitFor(() => expect(screen.getByTestId('flow-job-id')).toHaveTextContent('job-a'));\n    expect(agent.getDesktopFrame).not.toHaveBeenCalled();\n    expect(screen.getByTestId('flow-frame-job-id')).toHaveTextContent('none');\n    expect(screen.getByTestId('flow-frame-hash')).toHaveTextContent('none');\n\n    fireEvent.click(screen.getByRole('button', { name: 'Switch job' }));\n    await waitFor(() => expect(screen.getByTestId('flow-job-id')).toHaveTextContent('job-b'));\n    expect(agent.getDesktopFrame).not.toHaveBeenCalled();\n    expect(screen.getByTestId('flow-frame-job-id')).toHaveTextContent('none');\n    expect(screen.getByTestId('flow-frame-hash')).toHaveTextContent('none');\n  });\n""",
)

# The revision label belongs inside the build stage. Keep one global ARG for a
# default, then redeclare it after FROM so LABEL can expand it.
replace_once(
    'containers/sovereign-desktop-worker/Dockerfile',
    'ARG SOVEREIGN_SOURCE_REVISION=unverified\nARG SOVEREIGN_SOURCE_REVISION\nLABEL org.opencontainers.image.revision=${SOVEREIGN_SOURCE_REVISION}\nFROM ',
    'ARG SOVEREIGN_SOURCE_REVISION=unverified\nFROM ',
)
dockerfile = ROOT / 'containers/sovereign-desktop-worker/Dockerfile'
docker_text = dockerfile.read_text('utf-8')
first_line_end = docker_text.find('\n', docker_text.find('FROM '))
if first_line_end < 0:
    raise SystemExit('desktop Dockerfile FROM line missing')
docker_text = (
    docker_text[: first_line_end + 1]
    + 'ARG SOVEREIGN_SOURCE_REVISION\n'
    + 'LABEL org.opencontainers.image.revision=${SOVEREIGN_SOURCE_REVISION}\n'
    + docker_text[first_line_end + 1 :]
)
dockerfile.write_text(docker_text, 'utf-8')

print('BYTEBOT_LIVE_DESKTOP_TYPECHECK_FIXUP_APPLIED')
