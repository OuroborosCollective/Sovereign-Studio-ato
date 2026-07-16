#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import process from 'node:process';

const root = process.cwd();
const violations = [];

function read(path) {
  const absolute = `${root}/${path}`;
  if (!existsSync(absolute)) {
    violations.push(`${path}: required file is missing`);
    return '';
  }
  return readFileSync(absolute, 'utf8');
}

function requireText(path, source, fragment, reason) {
  if (!source.includes(fragment)) violations.push(`${path}: ${reason}`);
}

function forbidText(path, source, fragment, reason) {
  if (source.includes(fragment)) violations.push(`${path}: ${reason}`);
}

function requirePattern(path, source, pattern, reason) {
  if (!pattern.test(source)) violations.push(`${path}: ${reason}`);
}

function forbidPattern(path, source, pattern, reason) {
  if (pattern.test(source)) violations.push(`${path}: ${reason}`);
}

function interfaceBody(path, source, interfaceName) {
  const start = source.indexOf(`export interface ${interfaceName}`);
  const open = source.indexOf('{', start);
  const close = source.indexOf('\n}', open);
  if (start < 0 || open < 0 || close < 0) {
    violations.push(`${path}: interface ${interfaceName} is missing or malformed`);
    return '';
  }
  return source.slice(open + 1, close);
}

function walk(directory) {
  if (!existsSync(directory)) return [];
  return readdirSync(directory).flatMap((entry) => {
    const absolute = `${directory}/${entry}`;
    return statSync(absolute).isDirectory() ? walk(absolute) : [absolute];
  });
}

const paths = {
  docs: 'docs/LLM_LANGUAGE_RUNTIME_BOUNDARY.md',
  types: 'src/features/product/runtime/sovereignCapabilityTypes.ts',
  capability: 'src/features/product/runtime/sovereignCapabilityRouter.ts',
  executor: 'src/features/product/runtime/sovereignExecutorRuntime.ts',
  bridge: 'src/runtime/sovereignExecutorBridgeRuntime.ts',
  operator: 'src/runtime/sovereignInternalOperatorRuntime.ts',
  builder: 'src/features/product/containers/BuilderContainer.tsx',
  liteLlm: 'src/features/product/runtime/sovereignLiteLlmIntentRuntime.ts',
  intelligence: 'src/runtime/RuntimeIntelligence.ts',
  patternGateway: 'backend/agent_runtime/pattern_gateway.py',
  quarantine: 'backend/are_inference.py',
};
const source = Object.fromEntries(Object.entries(paths).map(([key, path]) => [key, read(path)]));

requireText(paths.docs, source.docs, 'Das Online-LLM versteht und formuliert Sprache. Die Runtime handelt.', 'binding rule is missing');
requireText(paths.docs, source.docs, 'offline_fallback', 'offline fallback contract is missing');
requireText(paths.docs, source.docs, 'role: system', 'speaker-role contract is missing');

requireText(paths.types, source.types, 'export interface SovereignLanguageIntentEvidence', 'structured language evidence is missing');
requireText(paths.types, source.types, "'online_llm' | 'offline_fallback' | 'explicit_runtime_action'", 'evidence sources are not bounded');
forbidPattern(paths.types, interfaceBody(paths.types, source.types, 'CapabilityRouterInput'), /readonly\s+text\s*:/, 'CapabilityRouterInput receives raw text');

requireText(paths.capability, source.capability, 'classifyOfflineCapabilityIntent', 'offline capability classifier is not explicitly scoped');
requireText(paths.capability, source.capability, 'const intent = input.language.intent;', 'capability router does not consume structured intent');
forbidText(paths.capability, source.capability, 'function hasExplicitAgentIntent', 'legacy raw-text intent helper returned');

forbidPattern(paths.executor, interfaceBody(paths.executor, source.executor, 'SovereignExecutorRouteInput'), /readonly\s+text\s*:/, 'executor route receives raw text');
requireText(paths.executor, source.executor, 'classifyOfflineSovereignExecutorIntent', 'executor fallback is not explicitly offline');
forbidText(paths.executor, source.executor, 'classifySovereignExecutorIntent', 'unscoped executor classifier returned');

requireText(paths.bridge, source.bridge, 'intent: input.intent', 'bridge does not forward structured intent');
requireText(paths.bridge, source.bridge, 'taskComplexity: input.taskComplexity', 'bridge does not forward structured complexity');
forbidText(paths.bridge, source.bridge, 'text: input.text', 'bridge forwards raw user text');

forbidPattern(paths.operator, interfaceBody(paths.operator, source.operator, 'SovereignInternalOperatorInput'), /readonly\s+text\s*:/, 'internal operator receives raw text');
forbidText(paths.operator, source.operator, 'DOC_TOKENS', 'internal operator interprets document words');
forbidText(paths.operator, source.operator, 'CODE_TOKENS', 'internal operator interprets code words');

requireText(paths.liteLlm, source.liteLlm, 'readonly runtimeContext?: string;', 'LiteLLM request lacks runtime facts');
requireText(paths.liteLlm, source.liteLlm, 'Belegte Runtime-Fakten (nur Fakten, keine Sprachdeutung)', 'runtime context is not fact-bounded');
requireText(paths.builder, source.builder, 'fetchSovereignLiteLlmInterpretation({', 'Builder does not call the LiteLLM interpreter');
forbidText(paths.builder, source.builder, 'fetchDevChatWorkerInterpretation', 'Builder still calls the legacy language interpreter');
forbidText(paths.builder, source.builder, 'classifySovereignExecutorIntent', 'Builder uses the unscoped raw-text classifier');
requireText(paths.builder, source.builder, "appendChatLine({ role: 'system', text });", 'Builder lacks a dedicated runtime system notice');
requirePattern(paths.builder, source.builder, /const shouldUseOnlineLanguageUnderstanding\s*=/, 'online-first decision is missing');
const onlineDecisionCount = (source.builder.match(/const shouldUseOnlineLanguageUnderstanding\s*=/g) ?? []).length;
if (onlineDecisionCount !== 1) violations.push(`${paths.builder}: expected one online-first decision, found ${onlineDecisionCount}`);
forbidText(paths.builder, source.builder, 'Beratungsroute erkannt', 'runtime still speaks as the LLM');
requireText(paths.builder, source.builder, "appendRuntimeNotice(\"Runtime-Aktion autorisiert.", 'executor route state is not rendered through the runtime notice path');
requireText(paths.builder, source.builder, "role: 'system',\n          text: 'Schreibaktion blockiert.", 'write gate state is not rendered as system state');
forbidText(paths.builder, source.builder, "role: 'assistant',\n          text: 'Schreibauftrag erkannt.", 'legacy write interpretation is still rendered as assistant speech');
forbidText(paths.builder, source.builder, "role: 'assistant',\n                            text: 'Beratungsroute erkannt.", 'legacy advisory interpretation is still rendered as assistant speech');

requireText(paths.intelligence, source.intelligence, "if (this.state === 'half-open' && this.halfOpenProbeInFlight)", 'concurrent half-open probes are not blocked');
requireText(paths.intelligence, source.intelligence, 'Offline diagnostic rule evaluation only.', 'raw-text Runtime Intelligence is not marked offline-only');
for (const absolute of walk(`${root}/src`)) {
  const relative = absolute.slice(root.length + 1);
  if (!/\.(ts|tsx)$/.test(relative) || /\.test\.(ts|tsx)$/.test(relative)) continue;
  if (relative === paths.intelligence || relative === 'src/runtime/index.ts') continue;
  const body = readFileSync(absolute, 'utf8');
  if (/useRuntimeIntelligence\s*\(/.test(body)) {
    violations.push(`${relative}: Runtime Intelligence raw-text diagnostics entered a production UI path`);
  }
}

requireText(paths.patternGateway, source.patternGateway, 'blocker_evidence_passed: bool = False', 'blocker learning lacks explicit runtime evidence');
requireText(paths.patternGateway, source.patternGateway, 'and input_value.draft_pr_ready', 'solution learning lacks Draft-PR evidence');
requireText(paths.patternGateway, source.patternGateway, '"missionSha256"', 'learned pattern lacks causal mission hash');
requireText(paths.quarantine, source.quarantine, 'FROM are_learning_quarantine q', 'promotion is not bound to the target quarantine row');
requireText(paths.quarantine, source.quarantine, "c.payload->>'missionSha256'=BTRIM(q.prompt_sha256)", 'promotion accepts unrelated pattern evidence');

if (violations.length) {
  console.error('LLM / Runtime boundary gate failed:');
  for (const violation of violations) console.error(`- ${violation}`);
  process.exit(1);
}

console.log('LLM / Runtime boundary gate passed.');
