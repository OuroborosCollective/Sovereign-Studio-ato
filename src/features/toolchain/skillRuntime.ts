export interface ExplicitSkillInvocation {
  readonly name: string;
  readonly slug: string;
  readonly adaptedPrompt: string;
  readonly argument?: string;
  readonly skillId?: string;
  readonly sourceSha?: string;
  readonly contentSha256?: string;
}

function clean(value: string | undefined): string {
  return (value ?? '').trim();
}

export function buildExplicitSkillMission(input: ExplicitSkillInvocation): string {
  const name = clean(input.name);
  const slug = clean(input.slug).replace(/^\/+/, '');
  const adaptedPrompt = clean(input.adaptedPrompt);
  const argument = clean(input.argument);

  if (!name || !slug || !adaptedPrompt) {
    throw new Error('Skill-Ausführung blockiert: Name, Slug oder Workflow fehlt.');
  }

  const provenance = [
    clean(input.skillId) ? `Persisted skill id: ${clean(input.skillId)}` : '',
    clean(input.sourceSha) ? `Source blob SHA: ${clean(input.sourceSha)}` : '',
    clean(input.contentSha256) ? `Installed prompt SHA-256: ${clean(input.contentSha256)}` : '',
  ].filter(Boolean);

  return [
    'Explicit Sovereign skill invocation.',
    `Selected skill: ${name} (/${slug})`,
    ...provenance,
    '',
    'Apply the following installed workflow instructions only to this explicit invocation:',
    adaptedPrompt,
    '',
    'User task:',
    argument || 'Apply this workflow to the current confirmed repository and runtime context.',
    '',
    'Runtime truth rules: do not claim execution, file changes, tests, deployment, or success without corresponding runtime evidence. Respect all normal security, repository, approval, billing, and Draft-PR gates.',
  ].join('\n');
}
