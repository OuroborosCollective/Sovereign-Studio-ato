import type { ExternalMemorySyncConfig, ExternalMemorySearchResult } from './externalMemorySync';
import type { SolutionPatternStore } from './solutionPatternMemory';
import { searchExternalMemory, pullExternalMemoryUpdates } from './externalMemorySync';
import { matchSolutionPatterns } from './solutionPatternMemory';

export interface SovereignMemoryContextInput {
  mission: string;
  repoPaths: string[];
  config: ExternalMemorySyncConfig;
  solutionPatternStore: SolutionPatternStore | null;
  fetcher?: typeof fetch;
}

export interface SovereignMemoryContextResult {
  ok: boolean;
  source: 'remote-memory' | 'pattern-memory' | 'none';
  contextLines: string[];
  summary: string;
}

/**
 * Build memory context lines from remote memory search results
 */
function buildContextFromRemoteMemory(searchResult: ExternalMemorySearchResult): string[] {
  if (!searchResult.ok || searchResult.items.length === 0) {
    return [];
  }

  return searchResult.items.map(item => {
    const tags = item.tags.length > 0 ? ` [tags: ${item.tags.join(', ')}]` : '';
    return `REMOTE PATTERN:${tags}\n${item.text}`;
  });
}

/**
 * Build memory context lines from local pattern memory
 */
function buildContextFromPatternMemory(patternStore: SolutionPatternStore | null, mission: string): string[] {
  if (!patternStore || patternStore.patterns.length === 0) {
    return [];
  }

  // Match patterns based on the mission
  const matches = matchSolutionPatterns(patternStore, {
    description: mission,
    limit: 5
  });

  return matches.map(match => {
    const tags = match.pattern.tags.length > 0 ? ` [tags: ${match.pattern.tags.join(', ')}]` : '';
    return `LOCAL PATTERN:${tags}\n${match.aha}`;
  });
}

/**
 * Search and pull external memory updates to build context for LLM prompts
 */
export async function buildSovereignMemoryContext(input: SovereignMemoryContextInput): Promise<SovereignMemoryContextResult> {
  // If remote memory is not enabled or consent not accepted, fall back to pattern memory
  if (!input.config.enabled || !input.config.consentAccepted) {
    const patternContext = buildContextFromPatternMemory(input.solutionPatternStore, input.mission);
    return {
      ok: patternContext.length > 0,
      source: patternContext.length > 0 ? 'pattern-memory' : 'none',
      contextLines: patternContext,
      summary: patternContext.length > 0 
        ? `Built context from ${patternContext.length} local patterns` 
        : 'No memory context available'
    };
  }

  try {
    // First try to search external memory
    const searchResult = await searchExternalMemory({
      config: input.config,
      query: input.mission,
      limit: 8,
      fetcher: input.fetcher
    });

    if (searchResult.ok && searchResult.items.length > 0) {
      const contextLines = buildContextFromRemoteMemory(searchResult);
      return {
        ok: true,
        source: 'remote-memory',
        contextLines,
        summary: `Built context from ${contextLines.length} remote patterns`
      };
    }

    // If search didn't return results, try pulling updates
    if (input.config.mode === 'pull-only' || input.config.mode === 'push-pull') {
      const pullResult = await pullExternalMemoryUpdates({
        config: input.config,
        fetcher: input.fetcher
      });

      if (pullResult.ok && pullResult.items.length > 0) {
        const contextLines = buildContextFromRemoteMemory({
          ...searchResult,
          items: pullResult.items
        });
        
        return {
          ok: true,
          source: 'remote-memory',
          contextLines,
          summary: `Built context from ${contextLines.length} pulled patterns`
        };
      }
    }

    // Fall back to local pattern memory
    const patternContext = buildContextFromPatternMemory(input.solutionPatternStore, input.mission);
    return {
      ok: patternContext.length > 0,
      source: patternContext.length > 0 ? 'pattern-memory' : 'none',
      contextLines: patternContext,
      summary: patternContext.length > 0 
        ? `Built context from ${patternContext.length} local patterns` 
        : 'No memory context available'
    };

  } catch (error) {
    // Soft fail - fall back to local pattern memory
    const patternContext = buildContextFromPatternMemory(input.solutionPatternStore, input.mission);
    return {
      ok: patternContext.length > 0,
      source: patternContext.length > 0 ? 'pattern-memory' : 'none',
      contextLines: patternContext,
      summary: `Remote memory failed, fell back to ${patternContext.length} local patterns: ${error instanceof Error ? error.message : 'Unknown error'}`
    };
  }
}