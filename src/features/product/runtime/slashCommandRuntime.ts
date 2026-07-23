export type SlashCommandAction =
  | 'analyze' | 'fix' | 'pr' | 'repo' | 'clear'
  | 'test' | 'templates' | 'export'
  | 'skills' | 'scan-skills' | 'skill-run';

export interface SlashCommandDefinition {
  readonly cmd: string;
  readonly label: string;
  readonly action: SlashCommandAction;
  readonly description: string;
  /** For dynamically installed skills — the full adapted prompt */
  readonly adapted_prompt?: string;
  /** marks a command as dynamically installed by the skill system */
  readonly is_skill?: boolean;
  /** persisted provenance used by the explicit runtime handoff */
  readonly skill_id?: string;
  readonly source_sha?: string;
  readonly content_sha256?: string;
}

/** Static built-in commands always available */
export const BUILTIN_SLASH_COMMANDS: readonly SlashCommandDefinition[] = [
  { cmd: '/analyze',     label: 'Analyze',       action: 'analyze',     description: 'Internen Review starten' },
  { cmd: '/fix',         label: 'Fix',           action: 'fix',         description: 'Fehler-Review starten' },
  { cmd: '/pr',          label: 'Draft PR',      action: 'pr',          description: 'Draft PR erstellen' },
  { cmd: '/repo',        label: 'Repo laden',    action: 'repo',        description: 'GitHub-Repo URL laden' },
  { cmd: '/clear',       label: 'Chat leeren',   action: 'clear',       description: 'Nur lokalen Chat löschen' },
  { cmd: '/test',        label: 'Tests',          action: 'test',        description: 'Echte Tests im Agent-Workspace ausführen' },
  { cmd: '/templates',   label: 'Templates',      action: 'templates',   description: 'Prompt-Bibliothek öffnen' },
  { cmd: '/export',      label: 'Export',         action: 'export',      description: 'Aktuelle Sitzung als Markdown exportieren' },
  { cmd: '/skills',      label: 'Skills',         action: 'skills',      description: 'Installierte Skills anzeigen' },
  { cmd: '/scan-skills', label: 'Skill-Scanner', action: 'scan-skills', description: 'Repo nach Skills scannen & installieren' },
];

/** @deprecated use BUILTIN_SLASH_COMMANDS — kept for compatibility */
export const SOVEREIGN_SLASH_COMMANDS = BUILTIN_SLASH_COMMANDS;

export interface ParsedSlashCommand {
  readonly command: SlashCommandDefinition;
  readonly argument: string;
}

export function shouldShowSlashMenu(value: string): boolean {
  const clean = value.trimStart();
  return clean.startsWith('/') && !clean.includes('\n');
}

/**
 * Returns matching slash commands for the current input.
 * Merges built-in commands with dynamically installed skill commands.
 */
export function matchingSlashCommands(
  value: string,
  dynamicSkills: readonly SlashCommandDefinition[] = [],
): readonly SlashCommandDefinition[] {
  const clean = value.trimStart().toLowerCase();
  if (!clean.startsWith('/')) return [];
  const all = [...BUILTIN_SLASH_COMMANDS, ...dynamicSkills];
  return all.filter(
    (command) => command.cmd.startsWith(clean) || clean.startsWith(`${command.cmd} `),
  );
}

/**
 * Parses a submitted slash command against built-in + dynamic skills.
 */
export function parseSlashCommand(
  value: string,
  dynamicSkills: readonly SlashCommandDefinition[] = [],
): ParsedSlashCommand | null {
  const clean = value.trim();
  if (!clean.startsWith('/')) return null;
  const all = [...BUILTIN_SLASH_COMMANDS, ...dynamicSkills];
  const command = all.find(
    (candidate) => clean === candidate.cmd || clean.startsWith(`${candidate.cmd} `),
  );
  if (!command) return null;
  return { command, argument: clean.slice(command.cmd.length).trim() };
}
