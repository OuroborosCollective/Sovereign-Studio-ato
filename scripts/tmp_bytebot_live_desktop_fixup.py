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

print('BYTEBOT_LIVE_DESKTOP_TYPECHECK_FIXUP_APPLIED')
