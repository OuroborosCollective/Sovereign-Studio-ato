import { beforeEach, describe, expect, it } from 'vitest';
import { useSkillsStore } from './useSkillsStore';

const secretWorkflow = 'PRIVATE_WORKFLOW_SENTINEL: inspect only the selected runtime family.';

describe('useSkillsStore explicit invocation boundary', () => {
  beforeEach(() => {
    useSkillsStore.getState().reset();
    useSkillsStore.setState({
      skills: [{
        id: 'skill-1',
        name: 'Runtime Hunt',
        slug: 'runtime-hunt',
        description: 'Evidence-based runtime hunt',
        source_repo: 'owner/repo',
        source_path: 'skills/runtime/SKILL.md',
        framework: 'openai',
        adapted_prompt: secretWorkflow,
        source_sha: 'blob-sha',
        content_sha256: 'a'.repeat(64),
        is_active: true,
        created_at: '2026-07-16T00:00:00.000Z',
      }],
      loaded: true,
    });
  });

  it('does not inject installed workflow text into unrelated worker context', () => {
    const context = useSkillsStore.getState().getActiveSkillContext();

    expect(context).toContain('/runtime-hunt');
    expect(context).toContain('nur bei ausdrücklichem Slash-Aufruf');
    expect(context).not.toContain(secretWorkflow);
  });

  it('keeps the full workflow and provenance on the explicit slash command', () => {
    const commands = useSkillsStore.getState().getSkillSlashCommands();

    expect(commands).toEqual([expect.objectContaining({
      cmd: '/runtime-hunt',
      adapted_prompt: secretWorkflow,
      skill_id: 'skill-1',
      source_sha: 'blob-sha',
      content_sha256: 'a'.repeat(64),
    })]);
  });
});
