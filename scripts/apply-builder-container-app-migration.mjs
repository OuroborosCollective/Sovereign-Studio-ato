#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';

const file = 'src/App.tsx';
let source = readFileSync(file, 'utf8');
let changed = false;

function replaceOnce(from, to) {
  if (source.includes(to)) return;
  if (!source.includes(from)) throw new Error(`Expected block not found in ${file}: ${from.slice(0, 120)}`);
  source = source.replace(from, to);
  changed = true;
}

replaceOnce(
  "import { RemoteMemoryContainer } from './features/product/containers/RemoteMemoryContainer';",
  "import { RemoteMemoryContainer } from './features/product/containers/RemoteMemoryContainer';\nimport { BuilderContainer } from './features/product/containers/BuilderContainer';",
);

replaceOnce(
  `      {activeTab === 'builder' ? (
        <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
          <h2 className="font-bold">Sovereign Action Builder</h2>
          <p className="mt-1 text-xs text-slate-400">{repoSnapshotStatus.reason}</p>
          <textarea
            className="mt-2 min-h-24 w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
            value={mission}
            onChange={(e) => setMission(e.target.value)}
            placeholder="Auftrag, z.B. README + Update History"
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <button onClick={generateRepoIdeas} disabled={actionDisabled} type="button">Ideen</button>
            <button onClick={generateErrorWorkflow} disabled={actionDisabled} type="button">Fehler</button>
            <button onClick={publishDraftPr} disabled={isPublishing || actionDisabled} type="button">
              {isPublishing ? 'Draft PR läuft...' : 'Draft PR erstellen'}
            </button>
          </div>
          <pre className="mt-3 whitespace-pre-wrap rounded bg-black/40 p-3 text-xs text-slate-300">{sovereignSummary}</pre>
          {sovereignPreview ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400">Brain preview</summary>
              <pre className="mt-2 max-h-96 overflow-auto rounded bg-black/40 p-3 text-[11px] text-slate-300">{sovereignPreview}</pre>
            </details>
          ) : null}
        </section>
      ) : null}`,
  `      {activeTab === 'builder' ? (
        <BuilderContainer
          mission={mission}
          repoReady={repoSnapshotStatus.ready}
          repoReason={repoSnapshotStatus.reason}
          repoBusy={isRepoBusy}
          runtimeBusy={runtimeBusy}
          isPublishing={isPublishing}
          sovereignSummary={sovereignSummary}
          sovereignPreview={sovereignPreview}
          onMissionChange={setMission}
          onGenerateIdeas={generateRepoIdeas}
          onGenerateErrorWorkflow={generateErrorWorkflow}
          onPublishDraftPr={() => { void publishDraftPr(); }}
        />
      ) : null}`,
);

if (changed) {
  writeFileSync(file, source, 'utf8');
  console.log(`${file}: BuilderContainer migration applied`);
} else {
  console.log(`${file}: already migrated`);
}
