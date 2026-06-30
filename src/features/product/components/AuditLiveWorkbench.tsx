import React, { useMemo, useState } from 'react';
import { AndroidMessageBubble } from './AndroidMessageBubble';
import { DraftPrCard } from './DraftPrCard';
import { RepoTreeExplorer } from './RepoTreeExplorer';
import { SlashCommandMenu } from './SlashCommandMenu';
import { buildRepoDetectedHint, isSingleGithubRepoUrl, safeVibrate } from '../runtime/androidInteractionRuntime';
import { fetchDevChatRepoTree, parseDevChatGithubUrl, summarizeDevChatRepoSnapshot, type DevChatRepoSnapshot } from '../runtime/devChatWorkerBridge';
import { createRepoFilePrompt } from '../runtime/repoTreeExplorerRuntime';
import { matchingSlashCommands, parseSlashCommand } from '../runtime/slashCommandRuntime';
import type { BuilderContainerProps } from '../containers/BuilderContainer';

interface Line { readonly role: 'user' | 'assistant'; readonly text: string }

export function AuditLiveWorkbench(props: BuilderContainerProps) {
  const [draft, setDraft] = useState(props.mission);
  const [lines, setLines] = useState<Line[]>([{ role: 'assistant', text: props.sovereignSummary }]);
  const [repo, setRepo] = useState<DevChatRepoSnapshot | null>(null);
  const [repoOpen, setRepoOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [slashIndex, setSlashIndex] = useState(0);
  const slashMatches = useMemo(() => matchingSlashCommands(draft), [draft]);
  const showSlash = draft.trimStart().startsWith('/') && slashMatches.length > 0;
  const repoHint = isSingleGithubRepoUrl(draft) ? buildRepoDetectedHint(draft) : '';

  async function loadRepo(value: string) {
    const parsed = parseDevChatGithubUrl(value);
    if (!parsed) { setLines((p) => [...p, { role: 'assistant', text: 'Keine gültige GitHub-Repo-URL erkannt.' }]); return; }
    const result = await fetchDevChatRepoTree(parsed);
    if (result.ok && result.snapshot) {
      setRepo(result.snapshot);
      props.onMissionChange(`Repo laden via Chat: ${result.snapshot.repoUrl}`);
      setLines((p) => [...p, { role: 'assistant', text: `Repo geladen. ${summarizeDevChatRepoSnapshot(result.snapshot)}` }]);
      safeVibrate(navigator, 25);
      return;
    }
    setLines((p) => [...p, { role: 'assistant', text: `Repo-Laden blockiert: ${result.error ?? 'unbekannt'}` }]);
  }

  async function submit(value: string) {
    const clean = value.trim();
    if (!clean) return;
    setDraft('');
    const slash = parseSlashCommand(clean);
    if (slash?.command.action === 'clear') { setLines([]); return; }
    if (slash?.command.action === 'repo') { await loadRepo(slash.argument); return; }
    if (slash?.command.action === 'analyze') { props.onGenerateIdeas(); return; }
    if (slash?.command.action === 'fix') { props.onGenerateErrorWorkflow(); return; }
    if (slash?.command.action === 'pr') { props.onPublishDraftPr(); props.onStartOpenHands?.(clean); return; }
    if (parseDevChatGithubUrl(clean)) { await loadRepo(clean); return; }
    setLines((p) => [...p, { role: 'user', text: clean }, { role: 'assistant', text: 'Auftrag übernommen. Worker-Antwort bleibt über den bestehenden Runtime-Pfad im BuilderContainer abgesichert.' }]);
  }

  return (
    <section data-testid="builder-container" style={{ height: '100dvh', display: 'flex', flexDirection: 'column', background: '#0e1116', color: '#cdd9e5', position: 'relative' }}>
      <header><strong>Sovereign</strong><button type="button" onClick={() => setRepoOpen(true)} disabled={!repo}>Repo</button><button type="button" onClick={() => setInspectorOpen(true)}>PAT/ORC/INT</button></header>
      <main style={{ flex: 1, overflowY: 'auto' }}>{lines.map((line, index) => <AndroidMessageBubble key={index} role={line.role} text={line.text} onQuote={(text) => setDraft(`&quot;${text.slice(0, 120)}&quot;\n\n`)} />)}{props.openhandsJob?.draftPrUrl ? <DraftPrCard url={props.openhandsJob.draftPrUrl} changedFiles={props.openhandsJob.changedFiles ?? []} onOpenBrowser={() => window.open(props.openhandsJob?.draftPrUrl, '_blank')} onDiscussInChat={() => setDraft('Erkläre mir die Änderungen im Draft PR.')} /> : null}</main>
      <form onSubmit={(event) => { event.preventDefault(); submit(draft); }}>{showSlash ? <SlashCommandMenu commands={slashMatches} selectedIndex={slashIndex} onSelect={(command) => submit(command.cmd)} /> : null}{repoHint ? <button type="button" onClick={() => loadRepo(draft)}>{repoHint}</button> : null}<textarea aria-label="Sovereign Chat Eingabe" value={draft} onChange={(event) => { setDraft(event.target.value); setSlashIndex(0); }} /><button type="submit">Senden</button></form>
      {repoOpen ? <RepoTreeExplorer snapshot={repo} onClose={() => setRepoOpen(false)} onFileClick={(path) => { setDraft(createRepoFilePrompt(path)); setRepoOpen(false); }} /> : null}
      {inspectorOpen ? <section role="dialog" aria-modal="true" data-testid="runtime-inspector-panel"><button type="button" onClick={() => setInspectorOpen(false)}>Schließen</button><h2>PAT</h2><p>Pattern Memory: honest empty state.</p><h2>ORC</h2><p>Routing: Worker Chat und OpenHands bei Code-Auftrag.</p><h2>INT</h2><p>{repo ? summarizeDevChatRepoSnapshot(repo) : 'Repo-Snapshot fehlt.'}</p></section> : null}
    </section>
  );
}

export default AuditLiveWorkbench;
