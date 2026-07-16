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

function walkFiles(directory) {
  if (!existsSync(directory)) return [];
  const files = [];
  for (const entry of readdirSync(directory)) {
    const absolute = `${directory}/${entry}`;
    if (statSync(absolute).isDirectory()) files.push(...walkFiles(absolute));
    else files.push(absolute);
  }
  return files;
}

const docsPath = 'docs/LLM_LANGUAGE_RUNTIME_BOUNDARY.md';
const typesPath = 'src/features/product/runtime/sovereignCapabilityTypes.ts';
const capabilityPath = 'src/features/product/runtime/sovereignCapabilityRouter.ts';
const executorPath = 'src/features/product/runtime/sovereignExecutorRuntime.ts';
const bridgePath = 'src/runtime/sovereignExecutorBridgeRuntime.ts';
const operatorPath = 'src/runtime/sovereignInternalOperatorRuntime.ts';
const builderPath = 'src/features/product/containers/BuilderContainer.tsx';
const workerPath = 'src/features/product/runtime/devChatWorkerBridge.ts';
const intelligencePath = 'src/runtime/RuntimeIntelligence.ts';
const patternGatewayPath = 'backend/agent_runtime/pattern_gateway.py';
const quarantinePath = 'backend/are_inference.py';
const allowedRuntimeEvidenceMethods = new Set([
  'setModelHealthAdapters',
  'getModelHealthReport',
  'getModelHealthFallbackResult',
  'getModelHealthFallbackState',
  'stopModelHealthMonitoring',
  'startModelHealthMonitoring',
  'checkModelHealth',
  'recordModelSuccessForFallback',
  'recordModelFailureForFallback',
  'assertModelHealthReady',
  'getBestAvailableModel',
]);

const docs = read(docsPath);
const types = read(typesPath);
const capability = read(capabilityPath);
const executor = read(executorPath);
const bridge = read(bridgePath);
const operator = read(operatorPath);
const builder = read(builderPath);
const worker = read(workerPath);
const intelligence = read(intelligencePath);
const patternGateway = read(patternGatewayPath);
const quarantine = read(quarantinePath);

requireText(docsPath, docs, 'Das Online-LLM versteht und formuliert Sprache. Die Runtime handelt.', 'the binding architecture rule is missing');
requireText(docsPath, docs, 'offline_fallback', 'the offline fallback contract is missing');
requireText(docsPath, docs, 'role: system', 'the system-versus-assistant rendering contract is missing');

requireText(typesPath, types, 'export interface SovereignLanguageIntentEvidence', 'structured language evidence is missing');
requireText(typesPath, types, "readonly source: 'online_llm' | 'offline_fallback' | 'explicit_runtime_action';", 'language evidence source is not bounded');
requirePattern(typesPath, types, /export interface CapabilityRouterInput\s*\{\s*readonly language: SovereignLanguageIntentEvidence;/m, 'CapabilityRouterInput must start from structured language evidence');
forbidPatternInInterface(typesPath, types, 'CapabilityRouterInput', /readonly\s+text\s*:/, 'CapabilityRouterInput must not receive raw user text');

requireText(capabilityPath, capability, 'classifyOfflineCapabilityIntent', 'offline classifier is not explicitly named');
requireText(capabilityPath, capability, 'buildOfflineCapabilityLanguageEvidence', 'offline evidence builder is missing');
requireText(capabilityPath, capability, 'const intent = input.language.intent;', 'capability routing does not consume structured intent evidence');
forbidText(capabilityPath, capability, 'function hasExplicitAgentIntent', 'capability router still interprets raw language through a legacy helper');

requirePattern(executorPath, executor, /export interface SovereignExecutorRouteInput\s*\{\s*readonly intent: SovereignExecutorIntentKind;/m, 'executor route input must begin with structured intent');
forbidPatternInInterface(executorPath, executor, 'SovereignExecutorRouteInput', /readonly\s+text\s*:/, 'executor route input must not receive raw user text');
requireText(executorPath, executor, 'classifyOfflineSovereignExecutorIntent', 'executor fallback classifier is not explicitly offline');
forbidText(executorPath, executor, 'classifySovereignExecutorIntent', 'legacy unscoped executor classifier returned');

requireText(bridgePath, bridge, 'intent: input.intent', 'executor bridge does not forward structured intent');
requireText(bridgePath, bridge, 'taskComplexity: input.taskComplexity', 'executor bridge does not forward structured complexity');
forbidText(bridgePath, bridge, 'text: input.text', 'executor bridge still forwards raw user text');

requirePattern(operatorPath, operator, /export interface SovereignInternalOperatorInput\s*\{\s*readonly intent: SovereignExecutorIntentKind;/m, 'internal operator must consume structured intent');
forbidPatternInInterface(operatorPath, operator, 'SovereignInternalOperatorInput', /readonly\s+text\s*:/, 'internal operator must not receive raw user text');
forbidText(operatorPath, operator, 'DOC_TOKENS', 'internal operator still contains document-language tokens');
forbidText(operatorPath, operator, 'CODE_TOKENS', 'internal operator still contains code-language tokens');

requireText(workerPath, worker, 'readonly runtimeContext?: string;', 'worker interpretation input lacks evidence-backed runtime facts');
requireText(workerPath, worker, 'Belegte Runtime-Fakten (nur Fakten, keine Sprachdeutung)', 'runtime context is not explicitly constrained to facts');

requireText(builderPath, builder, 'const appendRuntimeNotice', 'BuilderContainer lacks a dedicated system notice path');
requireText(builderPath, builder, "appendChatLine({ role: 'system', text });", 'runtime notices are not rendered as system state');
requireText(builderPath, builder, 'runtimeContext: [', 'online interpretation does not receive runtime evidence');
requireText(builderPath, builder, "source: 'offline_fallback'", 'offline fallback evidence is not explicitly marked');
forbidText(builderPath, builder, 'classifySovereignExecutorIntent', 'legacy runtime language classifier returned to BuilderContainer');
forbidText(builderPath, builder, 'Beratungsroute erkannt', 'runtime still speaks as the model');
forbidPattern(builderPath, builder, /role:\s*['"]assistant['"][\s\S]{0,220}(?:Runtime-Aktion|Route blockiert|GitHub-Zugang ist bereit|Executor blockiert|Direct GitHub Patch fehlgeschlagen)/m, 'runtime/gate/tool state is still emitted as an assistant message');

requireText(intelligencePath, intelligence, 'Offline diagnostic rule evaluation only.', 'Runtime Intelligence text rules are not explicitly offline-only');
requireText(intelligencePath, intelligence, "if (this.state === 'half-open' && this.halfOpenProbeInFlight)", 'half-open circuit boundary does not reject concurrent probes');
for (const absolute of walkFiles(`${root}/src`)) {
  const relative = absolute.slice(root.length + 1);
  if (!/\.(ts|tsx)$/.test(relative) || /\.test\.(ts|tsx)$/.test(relative)) continue;
  if (relative === intelligencePath || relative === 'src/runtime/index.ts') continue;
  const source = readFileSync(absolute, 'utf8');
  if (/\buseRuntimeIntelligence\s*\(/.test(source)) {
    violations.push(`${relative}: useRuntimeIntelligence must remain outside online production language paths`);
  }
  for (const match of source.matchAll(/\bruntimeIntelligence\.([A-Za-z_$][\w$]*)/g)) {
    const method = match[1];
    if (!allowedRuntimeEvidenceMethods.has(method)) {
      violations.push(`${relative}: RuntimeIntelligence.${method} is not an allowed evidence or model-health capability`);
    }
  }
}

requireText(patternGatewayPath, patternGateway, 'blocker_evidence_passed: bool = False', 'blocker learning lacks explicit runtime-evidence state');
requireText(patternGatewayPath, patternGateway, 'and input_value.draft_pr_ready', 'solution learning does not require Draft-PR evidence');
requireText(patternGatewayPath, patternGateway, '"missionSha256"', 'learned patterns are not causally hash-bound to their mission');
requireText(quarantinePath, quarantine, 'FROM are_learning_quarantine q', 'quarantine promotion is not bound to the target quarantine row');
requireText(quarantinePath, quarantine, "c.payload->>'missionSha256'=BTRIM(q.prompt_sha256)", 'quarantine promotion accepts unrelated pattern evidence');

if (violations.length > 0) {
  console.error('LLM / Runtime boundary gate failed:');
  for (const violation of violations) console.error(`- ${violation}`);
  process.exit(1);
}

console.log('LLM / Runtime boundary gate passed.');

function forbidPatternInInterface(path, source, interfaceName, pattern, reason) {
  const start = source.indexOf(`export interface ${interfaceName}`);
  if (start < 0) {
    violations.push(`${path}: interface ${interfaceName} is missing`);
    return;
  }
  const open = source.indexOf('{', start);
  const close = source.indexOf('\n}', open);
  if (open < 0 || close < 0) {
    violations.push(`${path}: interface ${interfaceName} cannot be parsed by the gate`);
    return;
  }
  const body = source.slice(open + 1, close);
  if (pattern.test(body)) violations.push(`${path}: ${reason}`);
}
