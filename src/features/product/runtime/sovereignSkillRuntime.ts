export const SOVEREIGN_SKILL_SCHEMA_VERSION = 'sovereign-skill.v1' as const;

export type SovereignSkillMode = 'ASSESS' | 'PROPOSE' | 'APPLY' | 'OPERATE';
export type SovereignSkillSourceKind = 'sovereign' | 'adapted_reference' | 'external_adapter';
export type SovereignReferenceLoadPolicy = 'on_match' | 'on_step' | 'explicit_only';
export type SovereignSkillEffectClass = 'read_only' | 'workspace_mutation' | 'external_mutation';

export interface SovereignSkillReferenceV1 {
  readonly path: string;
  readonly blobHash: string;
  readonly loadPolicy: SovereignReferenceLoadPolicy;
}

export interface SovereignSkillScriptV1 {
  readonly path: string;
  readonly blobHash: string;
  readonly effectClass: SovereignSkillEffectClass;
}

export interface SovereignSkillManifestV1 {
  readonly schemaVersion: typeof SOVEREIGN_SKILL_SCHEMA_VERSION;
  readonly skillId: string;
  readonly version: string;
  readonly sourceKind: SovereignSkillSourceKind;
  readonly sourceRevision?: string;
  readonly description: string;
  readonly triggers: readonly string[];
  readonly antiTriggers: readonly string[];
  readonly modes: readonly SovereignSkillMode[];
  readonly requiredCapabilities: readonly string[];
  readonly forbiddenCapabilities: readonly string[];
  readonly requiredEvidence: readonly string[];
  readonly references: readonly SovereignSkillReferenceV1[];
  readonly scripts: readonly SovereignSkillScriptV1[];
  readonly ownerPolicyHash: string;
}

export interface SovereignSkillSummaryV1 {
  readonly schemaVersion: typeof SOVEREIGN_SKILL_SCHEMA_VERSION;
  readonly skillId: string;
  readonly version: string;
  readonly description: string;
  readonly triggers: readonly string[];
  readonly antiTriggers: readonly string[];
  readonly modes: readonly SovereignSkillMode[];
  readonly requiredCapabilities: readonly string[];
  readonly forbiddenCapabilities: readonly string[];
  readonly effects: readonly SovereignSkillEffectClass[];
  readonly manifestHash: string;
}

export type SovereignSkillCandidateStatus =
  | 'SELECTED'
  | 'NOT_MATCHED'
  | 'BLOCKED_ANTI_TRIGGER'
  | 'BLOCKED_CONTEXT_TRUST'
  | 'BLOCKED_CAPABILITY_STAGE'
  | 'BLOCKED_OWNER_POLICY';

export interface SovereignSkillCandidateDecision {
  readonly status: SovereignSkillCandidateStatus;
  readonly skillId: string;
  readonly manifestHash: string;
  readonly matchedTriggers: readonly string[];
  readonly matchedAntiTriggers: readonly string[];
  readonly missingCapabilities: readonly string[];
  readonly reason: string;
}

export interface SovereignLoadedSkillReference {
  readonly repositoryRevision: string;
  readonly path: string;
  readonly declaredBlobHash: string;
  readonly observedSha256: string;
  readonly owner: string;
  readonly trustClass: 'owner' | 'runtime_attested' | 'repository_attested';
  readonly truthBoundary: string;
  readonly skillId: string;
  readonly manifestHash: string;
  readonly workflowStep: string;
  readonly loadReason: string;
  readonly content: string;
}

const HASH_PATTERN = /^(?:[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64})$/;
const SKILL_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{1,119}$/;
const VERSION_PATTERN = /^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$/;
const SAFE_PATH_PATTERN = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[^\u0000]+$/;
const MANIFEST_FIELDS = new Set([
  'schemaVersion', 'skillId', 'version', 'sourceKind', 'sourceRevision', 'description',
  'triggers', 'antiTriggers', 'modes', 'requiredCapabilities', 'forbiddenCapabilities',
  'requiredEvidence', 'references', 'scripts', 'ownerPolicyHash',
]);

function requireString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value.trim();
}

function uniqueStrings(value: unknown, label: string, allowEmpty = false): readonly string[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  const normalized = value.map((item) => requireString(item, `${label}[]`));
  if (!allowEmpty && normalized.length === 0) throw new Error(`${label} must not be empty`);
  if (new Set(normalized).size !== normalized.length) throw new Error(`${label} must not contain duplicates`);
  return Object.freeze(normalized);
}

function boundHash(value: unknown, label: string): string {
  const normalized = requireString(value, label).toLowerCase();
  if (!HASH_PATTERN.test(normalized)) throw new Error(`${label} must be revision or SHA-256 bound`);
  return normalized;
}

function repositoryPath(value: unknown, label: string): string {
  const normalized = requireString(value, label).replace(/\\/g, '/');
  if (!SAFE_PATH_PATTERN.test(normalized)) throw new Error(`${label} must remain repository-relative`);
  return normalized;
}

function canonicalize(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(',')}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, item]) => item !== undefined)
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
  return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${canonicalize(item)}`).join(',')}}`;
}

async function sha256(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function parseSovereignSkillManifestV1(payload: unknown): SovereignSkillManifestV1 {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('manifest must be an object');
  }
  const source = payload as Record<string, unknown>;
  const unknown = Object.keys(source).filter((field) => !MANIFEST_FIELDS.has(field));
  if (unknown.length > 0) throw new Error(`manifest contains unknown fields: ${unknown.sort().join(', ')}`);
  if (source.schemaVersion !== SOVEREIGN_SKILL_SCHEMA_VERSION) throw new Error('unsupported schemaVersion');

  const skillId = requireString(source.skillId, 'skillId');
  if (!SKILL_ID_PATTERN.test(skillId)) throw new Error('skillId is not canonical');
  const version = requireString(source.version, 'version');
  if (!VERSION_PATTERN.test(version)) throw new Error('version must be semantic');
  const sourceKind = requireString(source.sourceKind, 'sourceKind') as SovereignSkillSourceKind;
  if (!['sovereign', 'adapted_reference', 'external_adapter'].includes(sourceKind)) {
    throw new Error('unsupported sourceKind');
  }
  const sourceRevision = source.sourceRevision == null || source.sourceRevision === ''
    ? undefined
    : boundHash(source.sourceRevision, 'sourceRevision');
  if (sourceKind !== 'sovereign' && !sourceRevision) throw new Error('non-sovereign sources require sourceRevision');

  const references = Array.isArray(source.references) ? source.references.map((raw, index) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error(`references[${index}] must be an object`);
    const item = raw as Record<string, unknown>;
    const fields = Object.keys(item).filter((field) => !['path', 'blobHash', 'loadPolicy'].includes(field));
    if (fields.length > 0) throw new Error(`references[${index}] contains unknown fields`);
    const loadPolicy = requireString(item.loadPolicy, `references[${index}].loadPolicy`) as SovereignReferenceLoadPolicy;
    if (!['on_match', 'on_step', 'explicit_only'].includes(loadPolicy)) throw new Error('unsupported reference loadPolicy');
    return Object.freeze({
      path: repositoryPath(item.path, `references[${index}].path`),
      blobHash: boundHash(item.blobHash, `references[${index}].blobHash`),
      loadPolicy,
    });
  }) : (() => { throw new Error('references must be an array'); })();

  const scripts = Array.isArray(source.scripts) ? source.scripts.map((raw, index) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error(`scripts[${index}] must be an object`);
    const item = raw as Record<string, unknown>;
    const fields = Object.keys(item).filter((field) => !['path', 'blobHash', 'effectClass'].includes(field));
    if (fields.length > 0) throw new Error(`scripts[${index}] contains unknown fields`);
    const effectClass = requireString(item.effectClass, `scripts[${index}].effectClass`) as SovereignSkillEffectClass;
    if (!['read_only', 'workspace_mutation', 'external_mutation'].includes(effectClass)) throw new Error('unsupported effectClass');
    return Object.freeze({
      path: repositoryPath(item.path, `scripts[${index}].path`),
      blobHash: boundHash(item.blobHash, `scripts[${index}].blobHash`),
      effectClass,
    });
  }) : (() => { throw new Error('scripts must be an array'); })();

  const modes = uniqueStrings(source.modes, 'modes') as readonly SovereignSkillMode[];
  if (modes.some((mode) => !['ASSESS', 'PROPOSE', 'APPLY', 'OPERATE'].includes(mode))) throw new Error('unsupported mode');
  const requiredCapabilities = uniqueStrings(source.requiredCapabilities, 'requiredCapabilities', true);
  const forbiddenCapabilities = uniqueStrings(source.forbiddenCapabilities, 'forbiddenCapabilities', true);
  if (requiredCapabilities.some((capability) => forbiddenCapabilities.includes(capability))) {
    throw new Error('capability cannot be both required and forbidden');
  }

  return Object.freeze({
    schemaVersion: SOVEREIGN_SKILL_SCHEMA_VERSION,
    skillId,
    version,
    sourceKind,
    ...(sourceRevision ? { sourceRevision } : {}),
    description: requireString(source.description, 'description'),
    triggers: uniqueStrings(source.triggers, 'triggers'),
    antiTriggers: uniqueStrings(source.antiTriggers, 'antiTriggers', true),
    modes,
    requiredCapabilities,
    forbiddenCapabilities,
    requiredEvidence: uniqueStrings(source.requiredEvidence, 'requiredEvidence', true),
    references: Object.freeze(references),
    scripts: Object.freeze(scripts),
    ownerPolicyHash: boundHash(source.ownerPolicyHash, 'ownerPolicyHash'),
  });
}

export async function summarizeSovereignSkill(manifest: SovereignSkillManifestV1): Promise<SovereignSkillSummaryV1> {
  const manifestHash = await sha256(canonicalize(manifest));
  return Object.freeze({
    schemaVersion: manifest.schemaVersion,
    skillId: manifest.skillId,
    version: manifest.version,
    description: manifest.description,
    triggers: manifest.triggers,
    antiTriggers: manifest.antiTriggers,
    modes: manifest.modes,
    requiredCapabilities: manifest.requiredCapabilities,
    forbiddenCapabilities: manifest.forbiddenCapabilities,
    effects: Object.freeze(Array.from(new Set(manifest.scripts.map((script) => script.effectClass))).sort()),
    manifestHash,
  });
}

function normalizedText(value: string): string {
  return (value.toLowerCase().match(/[a-z0-9_.:/-]+/g) ?? []).join(' ');
}

export async function resolveSovereignSkillCandidate(input: {
  readonly manifest: SovereignSkillManifestV1;
  readonly requestText: string;
  readonly stagedCapabilities: readonly string[];
  readonly contextTrust: 'owner' | 'runtime_attested' | 'repository_attested' | 'untrusted';
  readonly ownerPolicyHash: string;
}): Promise<SovereignSkillCandidateDecision> {
  const summary = await summarizeSovereignSkill(input.manifest);
  const text = normalizedText(input.requestText);
  const match = (phrase: string) => text.includes(normalizedText(phrase));
  const matchedTriggers = input.manifest.triggers.filter(match).sort();
  const matchedAntiTriggers = input.manifest.antiTriggers.filter(match).sort();
  const staged = new Set(input.stagedCapabilities);
  const missingCapabilities = input.manifest.requiredCapabilities.filter((capability) => !staged.has(capability)).sort();
  const forbiddenStaged = input.manifest.forbiddenCapabilities.some((capability) => staged.has(capability));

  const decision = (status: SovereignSkillCandidateStatus, reason: string): SovereignSkillCandidateDecision => Object.freeze({
    status,
    skillId: input.manifest.skillId,
    manifestHash: summary.manifestHash,
    matchedTriggers: Object.freeze(matchedTriggers),
    matchedAntiTriggers: Object.freeze(matchedAntiTriggers),
    missingCapabilities: Object.freeze(missingCapabilities),
    reason,
  });

  if (input.ownerPolicyHash !== input.manifest.ownerPolicyHash) return decision('BLOCKED_OWNER_POLICY', 'owner policy hash mismatch');
  if (input.contextTrust === 'untrusted') return decision('BLOCKED_CONTEXT_TRUST', 'context is not attested');
  if (matchedAntiTriggers.length > 0) return decision('BLOCKED_ANTI_TRIGGER', 'anti-trigger matched');
  if (matchedTriggers.length === 0) return decision('NOT_MATCHED', 'no trigger matched');
  if (missingCapabilities.length > 0 || forbiddenStaged) {
    return decision('BLOCKED_CAPABILITY_STAGE', 'run envelope capability stage rejected candidate');
  }
  return decision('SELECTED', 'candidate selected; permission and effect gates remain separate');
}

export function visibleSkillEffectsForMode(
  manifest: SovereignSkillManifestV1,
  mode: SovereignSkillMode,
): readonly SovereignSkillEffectClass[] {
  const allowed: Record<SovereignSkillMode, readonly SovereignSkillEffectClass[]> = {
    ASSESS: ['read_only'],
    PROPOSE: ['read_only'],
    APPLY: ['read_only', 'workspace_mutation'],
    OPERATE: ['read_only', 'workspace_mutation', 'external_mutation'],
  };
  const declared = new Set(manifest.scripts.map((script) => script.effectClass));
  return Object.freeze(allowed[mode].filter((effect) => declared.has(effect)));
}
