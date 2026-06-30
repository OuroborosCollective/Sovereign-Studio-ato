import { describe, expect, it } from 'vitest';
import { matchingSlashCommands, parseSlashCommand, shouldShowSlashMenu } from './slashCommandRuntime';

describe('slashCommandRuntime', () => {
  it('shows menu only for single-line slash drafts', () => {
    expect(shouldShowSlashMenu('/')).toBe(true);
    expect(shouldShowSlashMenu(' /an')).toBe(true);
    expect(shouldShowSlashMenu('/analyze\nnext')).toBe(false);
    expect(shouldShowSlashMenu('hello')).toBe(false);
  });

  it('matches available commands', () => {
    expect(matchingSlashCommands('/a').map((command) => command.cmd)).toEqual(['/analyze']);
    expect(matchingSlashCommands('/repo https://github.com/o/r').map((command) => command.cmd)).toEqual(['/repo']);
  });

  it('parses command arguments', () => {
    const parsed = parseSlashCommand('/repo https://github.com/o/r');
    expect(parsed?.command.action).toBe('repo');
    expect(parsed?.argument).toBe('https://github.com/o/r');
  });

  it('returns null for unknown commands', () => {
    expect(parseSlashCommand('/unknown')).toBeNull();
  });
});
