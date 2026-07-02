import { describe, expect, it } from 'vitest';
import { applyGitPatch, validateGitPatchRequest } from './gitPatchRuntime';

const FILE = 'src/foo.ts';
const CONTENT = `function hello() {
  return "world";
}

function goodbye() {
  return "farewell";
}
`;

describe('applyGitPatch — happy path', () => {
  it('applies a single block when search matches exactly once', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [{ search: 'return "world";', replace: 'return "earth";' }],
    });

    expect(result.ok).toBe(true);
    expect(result.errors).toEqual([]);
    expect(result.patched).toContain('return "earth";');
    expect(result.patched).not.toContain('return "world";');
    expect(result.blockResults[0].applied).toBe(true);
    expect(result.blockResults[0].matchCount).toBe(1);
  });

  it('applies multiple blocks in sequence', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [
        { search: 'return "world";', replace: 'return "earth";' },
        { search: 'return "farewell";', replace: 'return "bye";' },
      ],
    });

    expect(result.ok).toBe(true);
    expect(result.patched).toContain('return "earth";');
    expect(result.patched).toContain('return "bye";');
    expect(result.blockResults).toHaveLength(2);
    expect(result.blockResults.every(b => b.applied)).toBe(true);
  });

  it('dryRun returns patched content in patched field', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [{ search: 'return "world";', replace: 'return "moon";' }],
      dryRun: true,
    });

    expect(result.ok).toBe(true);
    expect(result.dryRun).toBe(true);
    expect(result.patched).toContain('return "moon";');
  });

  it('block applied in serial: second block can rely on first block result', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [
        { search: 'return "world";', replace: 'return "UNIQUE_MARKER";' },
        { search: 'return "UNIQUE_MARKER";', replace: 'return "final";' },
      ],
    });

    expect(result.ok).toBe(true);
    expect(result.patched).toContain('return "final";');
    expect(result.patched).not.toContain('UNIQUE_MARKER');
  });
});

describe('applyGitPatch — zero matches', () => {
  it('blocks when search string is not found', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [{ search: 'DOES_NOT_EXIST', replace: 'something' }],
    });

    expect(result.ok).toBe(false);
    expect(result.blockResults[0].applied).toBe(false);
    expect(result.blockResults[0].matchCount).toBe(0);
    expect(result.errors[0]).toContain('not found');
  });
});

describe('applyGitPatch — multiple matches', () => {
  it('blocks when search string matches more than once', () => {
    const dupeContent = `const x = "hello";\nconst y = "hello";\n`;
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: dupeContent,
      blocks: [{ search: '"hello"', replace: '"hi"' }],
    });

    expect(result.ok).toBe(false);
    expect(result.blockResults[0].matchCount).toBe(2);
    expect(result.errors[0]).toContain('matched 2 times');
  });
});

describe('applyGitPatch — validation errors', () => {
  it('rejects empty filePath', () => {
    const result = applyGitPatch({
      filePath: '',
      fileContent: CONTENT,
      blocks: [{ search: 'x', replace: 'y' }],
    });

    expect(result.ok).toBe(false);
    expect(result.errors[0]).toContain('filePath is required');
  });

  it('rejects empty blocks array', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [],
    });

    expect(result.ok).toBe(false);
    expect(result.errors[0]).toContain('non-empty array');
  });

  it('rejects when block count exceeds maxBlocks', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: Array.from({ length: 3 }, (_, i) => ({ search: `s${i}`, replace: `r${i}` })),
      maxBlocks: 2,
    });

    expect(result.ok).toBe(false);
    expect(result.errors[0]).toContain('Too many blocks');
  });

  it('rejects empty search string in a block', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [{ search: '', replace: 'something' }],
    });

    expect(result.ok).toBe(false);
    expect(result.errors[0]).toContain('search string is empty');
  });

  it('rejects search string exceeding maxSearchBytes', () => {
    const bigSearch = 'x'.repeat(100);
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [{ search: bigSearch, replace: 'y' }],
      maxSearchBytes: 50,
    });

    expect(result.ok).toBe(false);
    expect(result.errors[0]).toContain('exceeds 50 bytes');
  });

  it('rejects replace string exceeding maxReplaceBytes', () => {
    const bigReplace = 'x'.repeat(200);
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [{ search: 'return "world";', replace: bigReplace }],
      maxReplaceBytes: 100,
    });

    expect(result.ok).toBe(false);
    expect(result.errors[0]).toContain('exceeds 100 bytes');
  });

  it('stops at first failing block and does not apply subsequent blocks', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [
        { search: 'MISSING', replace: 'will_not_apply' },
        { search: 'return "world";', replace: 'return "earth";' },
      ],
    });

    expect(result.ok).toBe(false);
    expect(result.blockResults).toHaveLength(1);
    expect(result.patched).toBeUndefined();
  });
});

describe('applyGitPatch — secret masking in errors', () => {
  it('masks token-like strings from error snippets', () => {
    const result = applyGitPatch({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [{ search: 'ghp_abc12345678', replace: 'x' }],
    });

    expect(result.ok).toBe(false);
    expect(result.errors[0]).not.toContain('ghp_abc12345678');
    expect(result.errors[0]).toContain('****');
  });
});

describe('validateGitPatchRequest', () => {
  it('returns empty array for a valid request', () => {
    const errors = validateGitPatchRequest({
      filePath: FILE,
      fileContent: CONTENT,
      blocks: [{ search: 'return "world";', replace: 'return "earth";' }],
    });
    expect(errors).toEqual([]);
  });

  it('returns multiple errors for an invalid request', () => {
    const errors = validateGitPatchRequest({
      filePath: '',
      fileContent: CONTENT,
      blocks: [],
    });
    expect(errors.length).toBeGreaterThan(0);
    expect(errors.some(e => e.includes('filePath'))).toBe(true);
    expect(errors.some(e => e.includes('non-empty array'))).toBe(true);
  });
});
