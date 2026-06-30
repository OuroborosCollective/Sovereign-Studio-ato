export type SlashCommandAction = 'analyze' | 'fix' | 'pr' | 'repo' | 'clear';

export interface SlashCommandDefinition {
  readonly cmd: string;
  readonly label: string;
  readonly action: SlashCommandAction;
  readonly description: string;
}

export const SOVEREIGN_SLASH_COMMANDS: readonly SlashCommandDefinition[] = [
  { cmd: '/analyze', label: 'Analyze', action: 'analyze', description: 'Run internal review' },
  { cmd: '/fix', label: 'Fix', action: 'fix', description: 'Run error review' },
  { cmd: '/pr', label: 'Draft PR', action: 'pr', description: 'Start Draft PR task' },
  { cmd: '/repo', label: 'Load repo', action: 'repo', description: 'Load GitHub repo URL' },
  { cmd: '/clear', label: 'Clear chat', action: 'clear', description: 'Clear local chat only' },
];

export interface ParsedSlashCommand {
  readonly command: SlashCommandDefinition;
  readonly argument: string;
}

export function shouldShowSlashMenu(value: string): boolean {
  const clean = value.trimStart();
  return clean.startsWith('/') && !clean.includes('\n');
}

export function matchingSlashCommands(value: string): readonly SlashCommandDefinition[] {
  const clean = value.trimStart().toLowerCase();
  if (!clean.startsWith('/')) return [];
  return SOVEREIGN_SLASH_COMMANDS.filter((command) => command.cmd.startsWith(clean) || clean.startsWith(`${command.cmd} `));
}

export function parseSlashCommand(value: string): ParsedSlashCommand | null {
  const clean = value.trim();
  if (!clean.startsWith('/')) return null;
  const command = SOVEREIGN_SLASH_COMMANDS.find((candidate) => clean === candidate.cmd || clean.startsWith(`${candidate.cmd} `));
  if (!command) return null;
  return { command, argument: clean.slice(command.cmd.length).trim() };
}
