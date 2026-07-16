import { describe, expect, it } from 'vitest';
import { buildExplicitSkillMission } from './skillRuntime';

describe('explicit skill runtime handoff', () => {
  it('builds one evidence-gated mission only for the selected skill', () => {
    const mission = buildExplicitSkillMission({
      name: 'Runtime Hunt',
      slug: '/runtime-hunt',
      adaptedPrompt: 'Inspect the real runtime and rerun one failure family.',
      argument: 'Check the backend endpoint contract.',
      skillId: 'skill-123',
      sourceSha: 'abc123',
      contentSha256: 'f'.repeat(64),
    });

    expect(mission).toContain('Selected skill: Runtime Hunt (/runtime-hunt)');
    expect(mission).toContain('Inspect the real runtime and rerun one failure family.');
    expect(mission).toContain('Check the backend endpoint contract.');
    expect(mission).toContain('Persisted skill id: skill-123');
    expect(mission).toContain('Source blob SHA: abc123');
    expect(mission).toContain(`Installed prompt SHA-256: ${'f'.repeat(64)}`);
    expect(mission).toContain('do not claim execution');
  });

  it('fails closed when the persisted workflow is incomplete', () => {
    expect(() => buildExplicitSkillMission({
      name: 'Broken',
      slug: '/broken',
      adaptedPrompt: '',
    })).toThrow('Skill-Ausführung blockiert');
  });
});
