/**
 * Unit tests for Sovereign Studio Patch Worker
 * Tests the core SEARCH/REPLACE block logic
 */

interface PatchBlock {
  search: string;
  replace: string;
}

// Count exact occurrences of search string in content
function countMatches(content: string, search: string): number {
  if (!search) return 0;
  let count = 0;
  let index = 0;
  while ((index = content.indexOf(search, index)) !== -1) {
    count++;
    index += search.length;
  }
  return count;
}

// Apply SEARCH/REPLACE blocks to content (exits on 0 or >1 match)
function applyPatchBlocks(
  content: string, 
  blocks: PatchBlock[]
): { success: boolean; result?: string; error?: string; failedBlock?: number } {
  let result = content;
  
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    const matchCount = countMatches(result, block.search);
    
    if (matchCount === 0) {
      return { success: false, error: `Block ${i + 1}: SEARCH string not found`, failedBlock: i };
    }
    if (matchCount > 1) {
      return { success: false, error: `Block ${i + 1}: SEARCH string found ${matchCount} times (expected exactly 1)`, failedBlock: i };
    }
    
    result = result.replace(block.search, block.replace);
  }
  
  return { success: true, result };
}

// Forbidden path prefixes for security
const FORBIDDEN_PATHS = ['.git/', 'node_modules/', 'dist/', 'build/', '.env'];

function isPathSafe(path: string): boolean {
  const lower = path.toLowerCase();
  return !FORBIDDEN_PATHS.some(prefix => lower.startsWith(prefix));
}

// ============ TESTS ============

describe('Patch Worker Logic', () => {
  describe('countMatches', () => {
    it('counts single occurrence', () => {
      expect(countMatches('hello world', 'world')).toBe(1);
    });

    it('counts multiple occurrences', () => {
      expect(countMatches('foo bar foo', 'foo')).toBe(2);
    });

    it('returns 0 for no match', () => {
      expect(countMatches('hello world', 'xyz')).toBe(0);
    });

    it('returns 0 for empty search', () => {
      expect(countMatches('hello world', '')).toBe(0);
    });

    it('handles special characters', () => {
      const content = 'const x = `template`; const y = `template`;';
      expect(countMatches(content, '`template`')).toBe(2);
    });
  });

  describe('applyPatchBlocks', () => {
    it('applies single block successfully', () => {
      const content = 'const oldValue = 1;';
      const blocks: PatchBlock[] = [
        { search: 'const oldValue = 1;', replace: 'const newValue = 2;' }
      ];
      
      const result = applyPatchBlocks(content, blocks);
      
      expect(result.success).toBe(true);
      expect(result.result).toBe('const newValue = 2;');
    });

    it('applies multiple blocks sequentially', () => {
      const content = 'foo(); bar(); baz();';
      const blocks: PatchBlock[] = [
        { search: 'foo()', replace: 'FOO()' },
        { search: 'bar()', replace: 'BAR()' }
      ];
      
      const result = applyPatchBlocks(content, blocks);
      
      expect(result.success).toBe(true);
      expect(result.result).toBe('FOO(); BAR(); baz();');
    });

    it('fails when search string not found', () => {
      const content = 'hello world';
      const blocks: PatchBlock[] = [
        { search: 'not found', replace: 'replacement' }
      ];
      
      const result = applyPatchBlocks(content, blocks);
      
      expect(result.success).toBe(false);
      expect(result.error).toContain('not found');
      expect(result.failedBlock).toBe(0);
    });

    it('fails when search appears multiple times', () => {
      const content = 'const x = 1; const y = 1;';
      const blocks: PatchBlock[] = [
        { search: 'const x = 1;', replace: 'const x = 2;' }
      ];
      
      const result = applyPatchBlocks(content, blocks);
      
      expect(result.success).toBe(false);
      expect(result.error).toContain('found 2 times');
    });

    it('handles empty content', () => {
      const content = '';
      const blocks: PatchBlock[] = [
        { search: '', replace: 'something' }
      ];
      
      const result = applyPatchBlocks(content, blocks);
      
      // Empty search returns 0 matches, so it fails
      expect(result.success).toBe(false);
    });
  });

  describe('isPathSafe', () => {
    it('allows safe paths', () => {
      expect(isPathSafe('src/App.tsx')).toBe(true);
      expect(isPathSafe('src/features/test.ts')).toBe(true);
      expect(isPathSafe('docs/README.md')).toBe(true);
    });

    it('blocks .git paths', () => {
      expect(isPathSafe('.git/config')).toBe(false);
      expect(isPathSafe('.git/hooks/pre-commit')).toBe(false);
    });

    it('blocks node_modules paths', () => {
      expect(isPathSafe('node_modules/package/index.js')).toBe(false);
    });

    it('blocks dist/build paths', () => {
      expect(isPathSafe('dist/bundle.js')).toBe(false);
      expect(isPathSafe('build/output.css')).toBe(false);
    });

    it('blocks .env paths', () => {
      expect(isPathSafe('.env')).toBe(false);
      expect(isPathSafe('.env.local')).toBe(false);
    });

    it('is case-insensitive', () => {
      expect(isPathSafe('.GIT/config')).toBe(false);
      expect(isPathSafe('NODE_MODULES/package')).toBe(false);
    });
  });

  describe('BuilderContainer.test.tsx scenario', () => {
    it('replaces async test pattern', () => {
      const original = `    it('submits mission to OpenHands', async () => {
      render(<BuilderContainer />);
      await userEvent.click(screen.getByRole('button', { name: /start/i }));
    });`;

      const blocks: PatchBlock[] = [
        {
          search: `    it('submits mission to OpenHands', async () => {
      render(<BuilderContainer />);
      await userEvent.click(screen.getByRole('button', { name: /start/i }));
    });`,
          replace: `    it('submits mission to OpenHands', async () => {
      render(<BuilderContainer />);
      await userEvent.click(screen.getByRole('button', { name: /start/i }));
      
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /loading/i })).not.toBeInTheDocument();
      });
    });`
        }
      ];

      const result = applyPatchBlocks(original, blocks);
      
      expect(result.success).toBe(true);
      expect(result.result).toContain('waitFor');
      expect(result.result).toContain('queryByRole');
    });

    it('fails with ambiguous search (multiple matches)', () => {
      const content = `it('test 1', async () => { });
it('test 1', async () => { });`;

      const blocks: PatchBlock[] = [
        {
          search: `it('test 1', async () => { });`,
          replace: `it('test 1', async () => { /* modified */ });`
        }
      ];

      const result = applyPatchBlocks(content, blocks);
      
      expect(result.success).toBe(false);
      expect(result.error).toContain('found 2 times');
    });
  });
});

// Export for potential integration testing
export { countMatches, applyPatchBlocks, isPathSafe };