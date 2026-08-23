import { afterEach, describe, expect, it, vi } from 'vitest';
import { skillsApi } from './skillsApi';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('skillsApi endpoint contracts', () => {
  it('binds scan, read, adapt and install to typed POST requests', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/toolchain/skills/scan')) {
        return new Response(JSON.stringify({
          owner: 'acme',
          repo: 'skills',
          found: [],
          total: 0,
          frameworks_detected: [],
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/toolchain/skills/read')) {
        return new Response(JSON.stringify({
          content: '# Bounded skill',
          framework: 'agents',
          sha: 'a'.repeat(40),
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/toolchain/skills/adapt')) {
        return new Response(JSON.stringify({
          name: 'Bounded Skill',
          slug: 'bounded-skill',
          description: 'Review one bounded contract.',
          adapted_prompt: 'Review only the supplied contract.',
          framework: 'agents',
          source_sha: 'a'.repeat(40),
          content_sha256: 'b'.repeat(64),
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/toolchain/skills/install')) {
        return new Response(JSON.stringify({
          id: 'skill-1',
          slug: 'bounded-skill',
          skill: {
            id: 'skill-1',
            name: 'Bounded Skill',
            slug: 'bounded-skill',
            description: 'Review one bounded contract.',
            source_repo: 'acme/skills',
            source_path: 'SKILL.md',
            framework: 'agents',
            adapted_prompt: 'Review only the supplied contract.',
            source_sha: 'a'.repeat(40),
            content_sha256: 'b'.repeat(64),
            is_active: true,
            created_at: '2026-08-23T00:00:00Z',
          },
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({ error: 'unexpected endpoint' }), { status: 500 });
    });
    vi.stubGlobal('fetch', fetchMock);

    await skillsApi.scanRepo({ owner: 'acme', repo: 'skills', ref: 'main' });
    await skillsApi.readSkillFile({ owner: 'acme', repo: 'skills', path: 'SKILL.md', ref: 'main' });
    await skillsApi.adaptSkill({
      owner: 'acme',
      repo: 'skills',
      path: 'SKILL.md',
      raw_content: '# Bounded skill',
      framework: 'agents',
      source_sha: 'a'.repeat(40),
      ref: 'main',
    });
    await skillsApi.installSkill({
      name: 'Bounded Skill',
      slug: 'bounded-skill',
      description: 'Review one bounded contract.',
      source_repo: 'acme/skills',
      source_path: 'SKILL.md',
      framework: 'agents',
      adapted_prompt: 'Review only the supplied contract.',
      source_sha: 'a'.repeat(40),
      content_sha256: 'b'.repeat(64),
    });

    const calls = fetchMock.mock.calls.map(([input, init]) => ({
      url: String(input),
      init: init as RequestInit,
    }));
    expect(calls.map(call => call.url)).toEqual([
      'https://sovereign-backend.arelorian.de/api/toolchain/skills/scan',
      'https://sovereign-backend.arelorian.de/api/toolchain/skills/read',
      'https://sovereign-backend.arelorian.de/api/toolchain/skills/adapt',
      'https://sovereign-backend.arelorian.de/api/toolchain/skills/install',
    ]);
    expect(calls.every(call => call.init.method === 'POST')).toBe(true);
    expect(calls.every(call => call.init.credentials === 'include')).toBe(true);
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ owner: 'acme', repo: 'skills', ref: 'main' });
    expect(JSON.parse(String(calls[1].init.body))).toEqual({
      owner: 'acme',
      repo: 'skills',
      path: 'SKILL.md',
      ref: 'main',
    });
    expect(JSON.parse(String(calls[2].init.body))).toEqual(expect.objectContaining({
      path: 'SKILL.md',
      source_sha: 'a'.repeat(40),
    }));
    expect(JSON.parse(String(calls[3].init.body))).toEqual(expect.objectContaining({
      slug: 'bounded-skill',
      content_sha256: 'b'.repeat(64),
    }));
  });

  it('does not treat a rejected install as an installed skill', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: 'skill_install_blocked',
    }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    })));

    await expect(skillsApi.installSkill({
      name: 'Blocked Skill',
      slug: 'blocked-skill',
      description: 'Blocked by policy.',
      source_repo: 'acme/skills',
      source_path: 'SKILL.md',
      framework: 'agents',
      adapted_prompt: 'No action.',
      source_sha: 'a'.repeat(40),
      content_sha256: 'b'.repeat(64),
    })).rejects.toThrow('skill_install_blocked');
  });
});
