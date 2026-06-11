import { describe, it, expect } from 'vitest';
import { demoFiles, starterCards, defaultSettings, makeId } from './constants';

describe('Product Constants', () => {
  describe('makeId', () => {
    it('should generate a valid UUID', () => {
      const id = makeId();
      expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[4][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    });

    it('should generate unique IDs', () => {
      const id1 = makeId();
      const id2 = makeId();
      expect(id1).not.toBe(id2);
    });
  });

  describe('demoFiles', () => {
    it('should be an array', () => {
      expect(Array.isArray(demoFiles)).toBe(true);
    });

    it('should have at least one file', () => {
      expect(demoFiles.length).toBeGreaterThan(0);
    });

    it('should conform to FileItem interface', () => {
      demoFiles.forEach(file => {
        expect(typeof file.path).toBe('string');
        expect(file.path.length).toBeGreaterThan(0);
        expect(typeof file.icon).toBe('string');
        expect(file.icon.length).toBeGreaterThan(0);
      });
    });

    it('should have unique paths', () => {
      const paths = demoFiles.map(f => f.path);
      const uniquePaths = new Set(paths);
      expect(uniquePaths.size).toBe(paths.length);
    });
  });

  describe('starterCards', () => {
    it('should return an array of 4 cards', () => {
      const cards = starterCards();
      expect(cards).toHaveLength(4);
    });

    it('should return cards with unique IDs', () => {
      const cards = starterCards();
      const ids = cards.map(c => c.id);
      const uniqueIds = new Set(ids);
      expect(uniqueIds.size).toBe(ids.length);
    });

    it('should conform to Card interface', () => {
      const cards = starterCards();
      cards.forEach(card => {
        expect(typeof card.id).toBe('string');
        expect(card.id.length).toBeGreaterThan(0);
        expect(typeof card.title).toBe('string');
        expect(card.title.length).toBeGreaterThan(0);
        expect(typeof card.body).toBe('string');
        expect(card.body.length).toBeGreaterThan(0);
      });
    });
  });

  describe('defaultSettings', () => {
    it('should have expected default values', () => {
      expect(defaultSettings).toEqual({
        repoMode: 'monorepo',
        packageManager: 'pnpm',
        installStrategy: 'workspace',
        linter: 'auto',
        specialization: "React Vite Capacitor Android GitHub Actions Free First Router",
        maxFixLoops: 3,
      });
    });

    it('should have a positive maxFixLoops', () => {
      expect(defaultSettings.maxFixLoops).toBeGreaterThan(0);
    });
  });
});
