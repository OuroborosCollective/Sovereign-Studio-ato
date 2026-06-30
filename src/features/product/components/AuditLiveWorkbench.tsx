import React, { useMemo, useState } from 'react';
import { ChatMarkdown } from './ChatMarkdown';
import { DraftPrCard } from './DraftPrCard';
import { RepoTreeExplorer } from './RepoTreeExplorer';
import { SlashCommandMenu } from './SlashCommandMenu';
import { buildRepoDetectedHint, isSingleGithubRepoUrl, safeVibrate } from '../runtime/androidInteractionRuntime';
import { fetchDevChatRepoTree, fetchDevChatWorkerReply, parseDevChatGithubUrl, summarizeDevChatRepoSnapshot, type DevChatRepoSnapshot } from '../runtime/devChatWorkerBridge';
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
  const [busy, setBusy] = useState(false);
  const [slashIndex, setSlashIndex] = useState(0);
  const slashMatches = useMemo(() => matchingSlashCommands(draft), [draft]);
  const showSlash = draft.trimStart().startsWith('/') && slashMatches.length > 0;
  const repoHint = isSingleGithubRepoUrl(draft) ? buildRepoDetectedHint(draft) : '';

  async function loadRepo(value: string) {
    const parsed = parseDevChatGithubUrl(value);
    if (!parsed) {
      setLines((previous) => [...previous, { role: 'assistant', text: 'Keine gültige GitHub-Repo-URL erkannt.' }]);
      return;
    }
    setBusy(true);
    const result = await fetchDevChatRepoTree(parsed);
    setBusy(false);
    if (result.ok && result.snapshot) {
      setRepo(result.snapshot);
      props.onMissionChange(`Repo laden via Chat: ${result.snapshot.repoUrl}`);
      setLines((previous) => [...previous, { role: 'assistant', text: `Repo geladen. ${summarizeDevChatRepoSnapshot(result.snapshot)}` }]);
      safeVibrate(navigator, 25);
      return;
    }
    setLines((previous) => [...previous, { role: 'assistant', text: `Repo-Laden blockiert: ${result.error ?? 'unbekannt'}` }]);
  }

  async function sendText(value: string) {
    const clean = value.trim();
    if (!clean || busy) return;
    setDraft('');
    const slash = parseSlashCommand(clean);
    if (slash) {
      if (slash.command.action === 'clear') { setLines([]); return; }
      if (slash.command.action === 'repo') { await loadRepo(slash.argument); return; }
      if (slash.command.action === 'analyze') { props.onGenerateIdeas(); return; }
      if (slash.command.action === 'fix') { props.onGenerateErrorWorkflow(); return; }
      if (slash.command.action === 'pr') { props.onPublishDraftPr(); props.onStartOpenHands?.(clean); return; }
    }
    if (parseDevChatGithubUrl(clean)) { await loadRepo(clean); return; }
    setLines((previous) => [...previous, { role: 'user', text: clean }]);
    setBusy(true);
    const reply = await fetchDevChatWorkerReply({
      model: 'cerebras/gpt-oss-120b',
      messages: [{ role: 'system', content: repo ? `Repo: ${repo.owner}/${repo.repo}` : props.repoReason }, { role: 'user', content: clean }],
    });
    setBusy(false);
    setLines((previous) => [...previous, { role: 'assistant', text: reply.ok && reply.content ? reply.content : `Worker blockiert: ${reply.error ?? 'keine Antwort'}` }]);
  }

  return (
    <section data-testid="builder-container" style={{ height: '100dvh', display: 'flex', flexDirection: 'column', background: '#0e1116', color: '#cdd9e5', position: 'relative' }}>
      <header style={{ padding: 10, borderBottom: '1px solid #232d3a', display: 'flex', gap: 8 }}>
        <strong style={{ color: '#00d9b1' }}>Sovereign</strong>
        <span style={{ flex: 1, color: '#768390' }}>{repo ? summarizeDevChatRepoSnapshot(repo) : props.repoReason}</span>
        <button type="button" onClick={() => setRepoOpen(true)} disabled={!repo}>Repo</button>
        <button type="button" onClick={() => setInspectorOpen(true)}>PAT/ORC/INT</button>
      </header>
      <main style={{ flex: 1, overflowY: 'auto', padding: 10 }}>
        {lines.map((line, index) => <div key={index} style={{ margin: '8px 0', padding: 10, border: '1px solid #232d3a', borderRadius: 12 }}>{line.role === 'assistant' ? <ChatMarkdown content={line.text} /> : line.text}</div>)}
        {props.openhandsJob?.draftPrUrl ? <DraftPrCard url={props.openhandsJob.draftPrUrl} changedFiles={props.openhandsJob.changedFiles ?? []} onOpenBrowser={() => window.open(props.openhandsJob?.draftPrUrl, '_blank')} onDiscussInChat={() => setDraft('Erkläre mir die Änderungen im Draft PR.')} /> : null}
        {busy ? <p>Runtime arbeitet…</p> : null}
      </main>
      <form onSubmit={(event) => { event.preventDefault(); sendText(draft); }} style={{ padding: 10, borderTop: '1px solid #232d3a' }}>
        {showSlash ? <SlashCommandMenu commands={slashMatches} selectedIndex={slashIndex} onSelect={(command) => sendText(command.cmd)} /> : null}
        {repoHint ? <button type="button" onClick={() => loadRepo(draft)}>{repoHint}</button> : null}
        <textarea aria-label="Sovereign Chat Eingabe" value={draft} onChange={(event) => { setDraft(event.target.value); setSlashIndex(0); }} onKeyDown={(event) => {
          if (showSlash && event.key === 'ArrowDown') { event.preventDefault(); setSlashIndex((index) => Math.min(index + 1, slashMatches.length - 1)); }
          if (showSlash && event.key === 'ArrowUp') { event.preventDefault(); setSlashIndex((index) => Math.max(index - 1, 0)); }
          if (showSlash && event.key === 'Escape') { event.preventDefault(); setDraft(''); }
          if (showSlash && event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendText(slashMatches[slashIndex].cmd); }
        }} style={{ width: '100%', minHeight: 56 }} />
        <button type="submit" disabled={!draft.trim() || busy}>Senden</button>
      </form>
      {repoOpen ? <RepoTreeExplorer snapshot={repo} onClose={() => setRepoOpen(false)} onFileClick={(path) => { setDraft(createRepoFilePrompt(path)); setRepoOpen(false); }} /> : null}
      {inspectorOpen ? <section role="dialog" aria-modal="true" data-testid="runtime-inspector-panel"><button type="button" onClick={() => setInspectorOpen(false)}>Schließen</button><h2>PAT</h2><p>Pattern Memory: honest empty state.</p><h2>ORC</h2><p>Routing: Worker Chat und OpenHands bei Code-Auftrag.</p><h2>INT</h2><p>{repo ? summarizeDevChatRepoSnapshot(repo) : 'Repo-Snapshot fehlt.'}</p></section> : null}
    </section>
  );
}

export default AuditLiveWorkbench;
