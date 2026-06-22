import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runSovereignLlmRuntime, buildSovereignLlmPrompt } from './sovereignLlmRuntime';

describe('sovereignLlmRuntime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should attempt providers in the correct order', async () => {
    const input = {
      mission: 'fix runtime issues',
      repoPaths: ['src/App.tsx'],
      selectedFilePath: 'README.md',
      memoryContext: [] as string[],
      runtimeEvents: [] as string[],
      allowUserKeyRoutes: false,
    };

    // Mock the provider calls to fail
    const mockCallMlvoCa = vi.fn().mockRejectedValue(new Error('MLVOCA failed'));
    const mockCallPollinations = vi.fn().mockRejectedValue(new Error('Pollinations failed'));
    
    // We can't easily inject mocks here since the functions are imported directly
    // In a real test we'd need to use a proper DI mechanism
    
    const result = await runSovereignLlmRuntime(input);

    expect(result.ok).toBe(false);
    expect(result.providerId).toBe('local-safe');
    expect(result.attempts).toHaveLength(2);
    expect(result.attempts[0].providerId).toBe('mlvoca');
    expect(result.attempts[1].providerId).toBe('pollinations');
  });

  it('should build proper prompt with all context', () => {
    const input = {
      mission: 'Create a new feature',
      repoPaths: ['src/App.tsx', 'src/index.ts'],
      selectedFilePath: 'README.md',
      memoryContext: ['Pattern: Fix runtime guards', 'Pattern: Improve package building'],
      runtimeEvents: ['package:build-start', 'guards:passed'],
      allowUserKeyRoutes: false,
    };

    const prompt = buildSovereignLlmPrompt(input);
    
    expect(prompt).toContain('Create a new feature');
    expect(prompt).toContain('src/App.tsx');
    expect(prompt).toContain('Pattern: Fix runtime guards');
    expect(prompt).toContain('package:build-start');
  });
});