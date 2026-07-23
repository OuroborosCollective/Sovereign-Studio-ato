export type ChangelogGroup = 'Added' | 'Changed' | 'Fixed' | 'Removed';

export interface ChangelogCommit {
  sha: string;
  message: string;
  changedFiles?: string[];
}

export interface ChangelogEntry {
  group: ChangelogGroup;
  text: string;
  sha: string;
}

function classify(message: string): ChangelogGroup {
  const value = message.toLowerCase();
  if (/\b(remove|removed|delete|deleted|deprecate)\b/.test(value)) return 'Removed';
  if (/\b(fix|fixed|repair|bug|regression|security)\b/.test(value)) return 'Fixed';
  if (/\b(add|added|create|introduce|implement|feature)\b/.test(value)) return 'Added';
  return 'Changed';
}

function cleanMessage(message: string): string {
  return message.replace(/^(feat|fix|chore|refactor|docs|test)(\([^)]*\))?:\s*/i, '').trim();
}

export function buildChangelogEntries(commits: readonly ChangelogCommit[]): ChangelogEntry[] {
  return commits
    .filter((commit) => commit.sha.trim() && commit.message.trim())
    .map((commit) => ({
      group: classify(commit.message),
      text: cleanMessage(commit.message),
      sha: commit.sha.slice(0, 12),
    }));
}

export function renderKeepAChangelog(
  version: string,
  date: string,
  commits: readonly ChangelogCommit[],
): string {
  const entries = buildChangelogEntries(commits);
  const lines = [`## [${version.trim() || 'Unreleased'}] - ${date}`, ''];
  for (const group of ['Added', 'Changed', 'Fixed', 'Removed'] as const) {
    const grouped = entries.filter((entry) => entry.group === group);
    if (!grouped.length) continue;
    lines.push(`### ${group}`, '');
    for (const entry of grouped) lines.push(`- ${entry.text} (${entry.sha})`);
    lines.push('');
  }
  if (!entries.length) lines.push('- No evidence-backed commit entries were available.', '');
  return lines.join('\n').trimEnd() + '\n';
}
