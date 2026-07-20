/**
 * Repo Insight Engine
 *
 * Autonomous repository analyzer that:
 * - Scans complete repository structure recursively
 * - Generates meaningful next-action suggestions from real runtime sources
 * - Creates safe concrete missions when user provides no specific request
 * - Translates technical repo state into beginner-friendly next steps
 *
 * Sources used (real runtime, no DOM, no mocks):
 * - repoFiles: Raw repository file tree from GitHub API
 * - scanRegistry: Existing scan findings from ScanFindingRegistry
 * - workflowReport: GitHub Actions status from WorkflowWatch
 * - telemetry: Runtime telemetry events
 * - solutionPatternStore: Learned solution patterns
 * - currentMission: User's current input (for placeholder detection)
 *
 * @module runtime/repoInsightEngine
 */

import type { RepoFile } from '../../github/types';
import type {
  ScanFinding,
  ScanFindingRegistry,
  ScanFindingCategory,
  ScanFindingSeverity,
} from './scanFindingRegistry';
import type {
  SolutionPatternStore,
  SolutionPatternMatch,
} from './solutionPatternMemory';
import { matchSolutionPatterns } from './solutionPatternMemory';
import type { WorkflowWatchReport } from './workflowWatch';

// ============================================================================
// Core Types
// ============================================================================

export type InsightRisk = 'niedrig' | 'mittel' | 'hoch';

export type InsightCategory = 'fix' | 'stabilitaet' | 'feature';

export interface RepoInsightSuggestion {
  id: string;
  category: InsightCategory;
  title: string;
  whyUseful: string;
  affectedFiles: string[];
  risk: InsightRisk;
  expectedBenefit: string;
  actionLabel: string;
  priority: number;
  fromFinding?: string;
}

export interface RepoInsightGroup {
  category: InsightCategory;
  label: string;
  suggestions: RepoInsightSuggestion[];
}

export interface RepoInsightEngineInput {
  repoFiles: RepoFile[];
  repoUrl?: string;
  repoBranch?: string;
  scanRegistry?: ScanFindingRegistry | null;
  workflowReport?: WorkflowWatchReport | null;
  telemetry?: TelemetryEventSnapshot | null;
  solutionPatternStore?: SolutionPatternStore | null;
  currentMission?: string;
}

export interface TelemetryEventSnapshot {
  eventCount: number;
  recentErrors: string[];
  guardFailures: number;
}

export interface RepoInsightEngineOutput {
  fixSuggestions: RepoInsightSuggestion[];
  hardeningSuggestions: RepoInsightSuggestion[];
  featureSuggestions: RepoInsightSuggestion[];
  recommendedMission: string;
  recommendedMissionConfidence: number;
  confidence: number;
  blockers: RepoInsightBlocker[];
  coachStatus: 'green' | 'yellow' | 'red';
  coachMessage: string;
  analyzedFiles: number;
  findings: RepoInsightFinding[];
}

export interface RepoInsightFinding {
  type: string;
  path?: string;
  description: string;
}

export interface RepoInsightBlocker {
  type: 'auth' | 'ci-failure' | 'critical-finding' | 'no-repo';
  message: string;
}

interface RepoStructureAnalysis {
  totalFiles: number;
  byExtension: Record<string, number>;
  byFolder: Record<string, number>;
  hasTests: boolean;
  hasAndroid: boolean;
  hasWebView: boolean;
  hasRuntime: boolean;
  hasComponents: boolean;
  hasWorkflows: boolean;
  hasReadme: boolean;
  missingReadme: boolean;
  missingTests: boolean;
  missingWorkflows: boolean;
  deepNesting: string[];
  deadCode: string[];
  duplicateLogic: string[];
  missingGuards: string[];
  missingValidations: string[];
  missingUserGuidance: string[];
  androidFiles: string[];
  runtimeFiles: string[];
  componentFiles: string[];
  testFiles: string[];
  workflowFiles: string[];
  configFiles: string[];
}

// ============================================================================
// Constants
// ============================================================================

const PLACEHOLDER_MISSION_PATTERNS = [
  /^m?ach?\s*(weiter|was\s+ich\s+hast)$/i,
  /^keine?\s*(ahnung|idee)$/i,
  /^start$/i,
  /^m?ach?\s*(was\s+du\s+willst)$/i,
  /^arbitrary$/i,
  /^example$/i,
  /^placeholder$/i,
  /^todo$/i,
  /^tbd$/i,
  /^fix\s+something$/i,
  /^(mach|make)\s*something$/i,
  /^improve\s*something$/i,
  /^optimiere$/i,
  /^verbessere$/i,
  /^überneh[mt]$/i,
];

const FORBIDDEN_PATTERNS = [
  /\b(ghp_|github_pat_|sk-|Bearer\s+)/,
  /password\s*[:=]/,
  /token\s*[:=]/,
];

const LOW_RISK_EXTENSIONS = new Set(['.md', '.json', '.yaml', '.yml', '.css', '.html']);
const MID_RISK_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx']);
const HIGH_RISK_EXTENSIONS = new Set(['.py', '.sh', '.rb', '.go', '.rs']);

const RUNTIME_INDICATOR_PATHS = [
  '/runtime/',
  'runtime.',
  'runtime-guard',
  'sequentialRuntime',
  'guard',
  'validation',
  'circuit',
  'telemetry',
];

const MOBILE_INDICATOR_PATHS = [
  '/android/',
  'capacitor',
  'mobile-',
  'webview',
  'device-profile',
  'mobileAgent',
  'mobileEntrypoint',
];

const COMPONENT_INDICATOR_PATHS = [
  '/components/',
  '.component.',
  '-component.',
  'Component',
  '/features/',
];

const TEST_INDICATOR_PATHS = [
  '.test.',
  '.spec.',
  '/tests/',
  '/e2e/',
  'test.ts',
  'test.tsx',
];

const WORKFLOW_INDICATOR_PATHS = [
  '.github/workflows/',
  '.gitlab-ci',
  'Jenkinsfile',
  '.circleci/',
];

// Hoisted CONFIG_NAMES array constant to the module level to avoid re-allocating on every check.
const CONFIG_NAMES = [
  'package.json',
  'tsconfig',
  'vite.config',
  'webpack.config',
  'jest.config',
  'eslint',
  'prettier',
  '.gitignore',
  '.env',
];

// ============================================================================
// Helper Functions
// ============================================================================

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function sanitizeText(value: string, maxLength = 200): string {
  let output = value.trim().slice(0, maxLength);
  for (const pattern of FORBIDDEN_PATTERNS) {
    output = output.replace(pattern, '<redacted>');
  }
  return output;
}

function isPlaceholderMission(mission: string): boolean {
  if (!mission || mission.length < 3) return true;
  const normalized = mission.toLowerCase().trim();
  return PLACEHOLDER_MISSION_PATTERNS.some((pattern) => pattern.test(normalized));
}

function extractFileExtension(path: string): string {
  const name = path.split('/').pop() ?? path;
  const index = name.lastIndexOf('.');
  return index >= 0 ? name.slice(index) : '';
}

function getRiskFromExtension(path: string): InsightRisk {
  const ext = extractFileExtension(path).toLowerCase();
  if (HIGH_RISK_EXTENSIONS.has(ext)) return 'hoch';
  if (MID_RISK_EXTENSIONS.has(ext)) return 'mittel';
  return 'niedrig';
}

// Accepts pre-lowercased file paths to eliminate redundant internal lowercasing operations in loop iteration.
function isRuntimePath(lowerPath: string): boolean {
  return RUNTIME_INDICATOR_PATHS.some((indicator) => lowerPath.includes(indicator));
}

function isMobilePath(lowerPath: string): boolean {
  return MOBILE_INDICATOR_PATHS.some((indicator) => lowerPath.includes(indicator));
}

function isComponentPath(lowerPath: string): boolean {
  return COMPONENT_INDICATOR_PATHS.some((indicator) => lowerPath.includes(indicator));
}

function isTestPath(lowerPath: string): boolean {
  return TEST_INDICATOR_PATHS.some((indicator) => lowerPath.includes(indicator));
}

function isWorkflowPath(lowerPath: string): boolean {
  return WORKFLOW_INDICATOR_PATHS.some((indicator) => lowerPath.includes(indicator));
}

function isConfigPath(lowerPath: string): boolean {
  const name = lowerPath.split('/').pop() ?? lowerPath;
  return CONFIG_NAMES.some((config) => name.includes(config));
}

function getNestingDepth(path: string): number {
  return path.split('/').filter(Boolean).length;
}

function extractFolderFromPath(path: string): string {
  const parts = path.split('/').filter(Boolean);
  return parts.slice(0, -1).join('/') || '/';
}

// ============================================================================
// Deep Structure Analysis
// ============================================================================

function analyzeRepoStructure(files: RepoFile[]): RepoStructureAnalysis {
  const byExtension: Record<string, number> = {};
  const byFolder: Record<string, number> = {};
  const deepNesting: string[] = [];
  const androidFiles: string[] = [];
  const runtimeFiles: string[] = [];
  const componentFiles: string[] = [];
  const testFiles: string[] = [];
  const workflowFiles: string[] = [];
  const configFiles: string[] = [];
  const nameCounts: Record<string, number> = {};

  let hasReadme = false;
  let hasTests = false;
  let hasAndroid = false;
  let hasWebView = false;
  let hasRuntime = false;
  let hasComponents = false;
  let hasWorkflows = false;

  for (const file of files) {
    const filePath = file.path;
    const path = filePath.toLowerCase();

    // Process the path split, nesting depth, folder name, and extensions in a single pass to reduce redundant string splits & arrays.
    const parts = filePath.split('/');
    const partsLen = parts.length;

    let depth = 0;
    for (let j = 0; j < partsLen; j++) {
      if (parts[j]) depth++;
    }

    const name = parts[partsLen - 1] || '';
    const dotIndex = name.lastIndexOf('.');
    const ext = dotIndex >= 0 ? name.slice(dotIndex) : '';

    // Count by extension
    if (ext) {
      byExtension[ext] = (byExtension[ext] ?? 0) + 1;
    }

    // Accumulate name counts for dead code detection on the fly to eliminate O(N) second files mapping pass.
    if (name) {
      const lowerName = name.toLowerCase();
      nameCounts[lowerName] = (nameCounts[lowerName] ?? 0) + 1;
    }

    // Count by folder
    const folder = partsLen > 1 ? parts.slice(0, -1).join('/') || '/' : '/';
    byFolder[folder] = (byFolder[folder] ?? 0) + 1;

    // Check deep nesting (more than 6 levels)
    if (depth > 6) {
      deepNesting.push(filePath);
    }

    // Categorize files using pre-lowercased file paths
    if (isMobilePath(path)) {
      if (path.includes('android')) androidFiles.push(filePath);
      if (path.includes('webview')) hasWebView = true;
      hasAndroid = true;
    }

    if (isRuntimePath(path)) {
      runtimeFiles.push(filePath);
      hasRuntime = true;
    }

    if (isComponentPath(path)) {
      componentFiles.push(filePath);
      hasComponents = true;
    }

    if (isTestPath(path)) {
      testFiles.push(filePath);
      hasTests = true;
    }

    if (isWorkflowPath(path)) {
      workflowFiles.push(filePath);
      hasWorkflows = true;
    }

    if (isConfigPath(path)) {
      configFiles.push(filePath);
    }

    // Check for README
    if (path === 'readme.md' || path === 'readme.txt') {
      hasReadme = true;
    }
  }

  // Detect potential issues
  const missingReadme = !hasReadme;
  const missingTests = !hasTests;
  const missingWorkflows = !hasWorkflows;

  // Retrieve potential dead code (duplicate names in different folders) from nameCounts.
  const duplicateLogic = Object.entries(nameCounts)
    .filter(([, count]) => count > 2)
    .map(([name]) => `* ${name}`);

  return {
    totalFiles: files.length,
    byExtension,
    byFolder,
    hasTests,
    hasAndroid,
    hasWebView,
    hasRuntime,
    hasComponents,
    hasWorkflows,
    hasReadme,
    missingReadme,
    missingTests,
    missingWorkflows,
    deepNesting: deepNesting.slice(0, 10),
    deadCode: duplicateLogic.slice(0, 10),
    duplicateLogic: duplicateLogic.slice(0, 10),
    missingGuards: [],
    missingValidations: [],
    missingUserGuidance: [],
    androidFiles,
    runtimeFiles,
    componentFiles,
    testFiles,
    workflowFiles,
    configFiles,
  };
}

// ============================================================================
// Suggestion Generators
// ============================================================================

function generateId(category: InsightCategory, title: string): string {
  return `insight-${category}-${stableHash(title).slice(0, 8)}`;
}

function generateFixSuggestions(
  structure: RepoStructureAnalysis,
  scanFindings: ScanFinding[],
  workflowReport: WorkflowWatchReport | null,
): RepoInsightSuggestion[] {
  const suggestions: RepoInsightSuggestion[] = [];
  let priority = 1;

  // From scan findings - high severity
  const highSeverityFindings = scanFindings.filter(
    (f) => f.severity === 'high' || f.severity === 'critical',
  );
  for (const finding of highSeverityFindings.slice(0, 3)) {
    suggestions.push({
      id: generateId('fix', finding.title),
      category: 'fix',
      title: sanitizeText(finding.title, 80),
      whyUseful: `Gefunden in ${sanitizeText(finding.filePath, 60)}: ${sanitizeText(finding.description, 100)}`,
      affectedFiles: [finding.filePath],
      risk: finding.severity === 'critical' ? 'hoch' : 'mittel',
      expectedBenefit: 'Stoppt potenzielle Probleme, bevor sie größer werden.',
      actionLabel: 'Reparieren lassen',
      priority: priority++,
      fromFinding: finding.id,
    });
  }

  // From workflow failures
  if (workflowReport?.checks) {
    const failedChecks = workflowReport.checks.filter(
      (check) => check.status === 'red' || check.status === 'pending',
    );
    for (const check of failedChecks.slice(0, 2)) {
      suggestions.push({
        id: generateId('fix', `workflow-${check.name}`),
        category: 'fix',
        title: `CI-Probleme: ${sanitizeText(check.name, 50)}`,
        whyUseful: `Workflow-Check "${check.name}" ist ${check.status === 'red' ? 'fehlgeschlagen' : 'noch nicht abgeschlossen'}.`,
        affectedFiles: ['.github/workflows/'],
        risk: check.status === 'red' ? 'hoch' : 'niedrig',
        expectedBenefit: 'CI-Pipeline wieder grün machen.',
        actionLabel: 'Workflow prüfen',
        priority: priority++,
      });
    }
  }

  // Missing README
  if (structure.missingReadme) {
    suggestions.push({
      id: generateId('fix', 'missing-readme'),
      category: 'fix',
      title: 'README fehlt',
      whyUseful: 'Ohne README wissen andere Entwickler nicht, wofür dieses Projekt gut ist.',
      affectedFiles: ['README.md'],
      risk: 'niedrig',
      expectedBenefit: 'Projekt wird verständlicher für alle.',
      actionLabel: 'README erstellen',
      priority: priority++,
    });
  }

  // Deep nesting warnings
  if (structure.deepNesting.length > 0) {
    suggestions.push({
      id: generateId('fix', 'deep-nesting'),
      category: 'fix',
      title: 'Tief verschachtelte Ordner gefunden',
      whyUseful: `Pfade mit mehr als 6 Ebenen können schwer zu navigieren sein.`,
      affectedFiles: structure.deepNesting.slice(0, 3),
      risk: 'niedrig',
      expectedBenefit: 'Ordnerstruktur wird einfacher zu verstehen.',
      actionLabel: 'Struktur flacher gestalten',
      priority: priority++,
    });
  }

  return suggestions;
}

/**
 * Generate pattern matches from learned solution patterns using Hebbian-style correlation.
 * Patterns that were successfully used are matched against current repo structure.
 */
function generatePatternMatches(
  patternStore: SolutionPatternStore | null | undefined,
  repoFiles: RepoFile[],
  byExtension?: Record<string, number>,
): SolutionPatternMatch[] {
  if (!patternStore || patternStore.patterns.length === 0) {
    return [];
  }

  // Retrieve the set of extensions. If byExtension map is pre-computed, we pull keys from it directly to save O(N) path splits.
  let repoExtensions: Set<string> | string[];
  if (byExtension) {
    repoExtensions = Object.keys(byExtension);
  } else {
    repoExtensions = new Set(
      repoFiles
        .map((f) => {
          const name = f.path.split('/').pop() ?? '';
          const idx = name.lastIndexOf('.');
          return idx >= 0 ? name.slice(idx) : '';
        })
        .filter(Boolean)
    );
  }

  // Slice the files first so we only allocate string paths for contextSignals we actually need (at most 50).
  const contextSignals = repoFiles.slice(0, 50).map((f) => f.path);

  // Match patterns using multiple queries for better coverage
  const allMatches: SolutionPatternMatch[] = [];

  // Query by file extensions present in repo
  for (const ext of repoExtensions) {
    const matches = matchSolutionPatterns(patternStore, {
      filePath: `file${ext}`,
      limit: 5,
    });
    allMatches.push(...matches);
  }

  // Query by repo paths
  const pathMatches = matchSolutionPatterns(patternStore, {
    contextSignals,
    limit: 10,
  });
  allMatches.push(...pathMatches);

  // Deduplicate by pattern ID and sort by score
  const seen = new Set<string>();
  const uniqueMatches: SolutionPatternMatch[] = [];
  for (const match of allMatches.sort((a, b) => b.score - a.score)) {
    if (!seen.has(match.pattern.id)) {
      seen.add(match.pattern.id);
      uniqueMatches.push(match);
    }
  }

  return uniqueMatches.slice(0, 10);
}

function generateHardeningSuggestions(
  structure: RepoStructureAnalysis,
  scanFindings: ScanFinding[],
): RepoInsightSuggestion[] {
  const suggestions: RepoInsightSuggestion[] = [];
  let priority = 1;

  // From scan findings - runtime guards needed
  const runtimeGuardsNeeded = scanFindings.filter(
    (f) => f.category === 'runtime-guard' || f.category === 'warning',
  );
  for (const finding of runtimeGuardsNeeded.slice(0, 3)) {
    suggestions.push({
      id: generateId('stabilitaet', finding.title),
      category: 'stabilitaet',
      title: sanitizeText(finding.title, 80),
      whyUseful: `Runtime-Schutz für ${sanitizeText(finding.filePath, 60)} verbessern.`,
      affectedFiles: [finding.filePath],
      risk: 'mittel',
      expectedBenefit: 'App wird stabiler und robuster.',
      actionLabel: 'Runtime härten',
      priority: priority++,
      fromFinding: finding.id,
    });
  }

  // Missing tests but has runtime files
  if (structure.missingTests && structure.hasRuntime) {
    suggestions.push({
      id: generateId('stabilitaet', 'runtime-without-tests'),
      category: 'stabilitaet',
      title: 'Runtime-Module ohne Tests',
      whyUseful: 'Runtime-Logik ohne Tests kann unerwartet brechen.',
      affectedFiles: structure.runtimeFiles.slice(0, 5),
      risk: 'mittel',
      expectedBenefit: 'Früherkennung von Problemen in Runtime-Code.',
      actionLabel: 'Tests hinzufügen',
      priority: priority++,
    });
  }

  // Has Android but missing mobile tests
  if (structure.hasAndroid && !structure.testFiles.some((f) => f.includes('mobile'))) {
    suggestions.push({
      id: generateId('stabilitaet', 'mobile-without-tests'),
      category: 'stabilitaet',
      title: 'Mobile App ohne dedizierte Tests',
      whyUseful: 'Android/WebView-Funktionen sollten getestet werden.',
      affectedFiles: structure.androidFiles.slice(0, 5),
      risk: 'mittel',
      expectedBenefit: 'Mobile App funktioniert zuverlässig auf Geräten.',
      actionLabel: 'Mobile Tests hinzufügen',
      priority: priority++,
    });
  }

  // Has runtime files
  if (structure.runtimeFiles.length > 0 && structure.runtimeFiles.length < 5) {
    suggestions.push({
      id: generateId('stabilitaet', 'runtime-expansion'),
      category: 'stabilitaet',
      title: 'Runtime-Module erweitern',
      whyUseful: 'Mehr Runtime-Guards machen die App sicherer.',
      affectedFiles: structure.runtimeFiles.slice(0, 3),
      risk: 'niedrig',
      expectedBenefit: 'Bessere Fehlerbehandlung und Validierung.',
      actionLabel: 'Runtime ausbauen',
      priority: priority++,
    });
  }

  // Missing workflow files
  if (structure.missingWorkflows) {
    suggestions.push({
      id: generateId('stabilitaet', 'missing-workflows'),
      category: 'stabilitaet',
      title: 'CI/CD Workflows fehlen',
      whyUseful: 'Ohne Workflows gibt es keine automatische Prüfung.',
      affectedFiles: ['.github/workflows/'],
      risk: 'mittel',
      expectedBenefit: 'Jeder Commit wird automatisch geprüft.',
      actionLabel: 'Workflows einrichten',
      priority: priority++,
    });
  }

  // Scan findings about validation
  const validationFindings = scanFindings.filter(
    (f) => f.category === 'type-error' || f.category === 'build-logic',
  );
  for (const finding of validationFindings.slice(0, 2)) {
    suggestions.push({
      id: generateId('stabilitaet', finding.title),
      category: 'stabilitaet',
      title: `Validierung verbessern: ${sanitizeText(finding.title, 60)}`,
      whyUseful: 'Bessere Typ-Prüfungen verhindern Runtime-Fehler.',
      affectedFiles: [finding.filePath],
      risk: 'mittel',
      expectedBenefit: 'Weniger unerwartete Fehler zur Laufzeit.',
      actionLabel: 'Validierung verstärken',
      priority: priority++,
      fromFinding: finding.id,
    });
  }

  return suggestions;
}

function generateFeatureSuggestions(
  structure: RepoStructureAnalysis,
  solutionPatterns: SolutionPatternMatch[],
): RepoInsightSuggestion[] {
  const suggestions: RepoInsightSuggestion[] = [];
  let priority = 1;

  // From successful solution patterns - include match score and relevance reasons
  for (const match of solutionPatterns.slice(0, 5)) {
    const pattern = match.pattern;
    // Show patterns that have been used successfully OR have high match score
    if (pattern.confidence === 'completed' || pattern.successfulUses > 0 || match.score >= 3) {
      const scoreLabel = match.score >= 5 ? '🟢' : match.score >= 3 ? '🟡' : '🔵';
      const successInfo = pattern.successfulUses > 0 ? ` (${pattern.successfulUses}x erfolgreich)` : '';
      suggestions.push({
        id: generateId('feature', pattern.problemSummary),
        category: 'feature',
        title: `${scoreLabel} ${sanitizeText(pattern.problemSummary, 65)}`,
        whyUseful: `${match.aha}${successInfo}. Grund: ${match.reasons.join(', ')}.`,
        affectedFiles: [pattern.filePathHint],
        risk: 'niedrig',
        expectedBenefit: 'Bewährte Lösung wird wiederverwendet.',
        actionLabel: 'Pattern anwenden',
        priority: priority++,
      });
    }
  }

  // Has Android but no WebView tests
  if (structure.hasAndroid && !structure.hasWebView) {
    suggestions.push({
      id: generateId('feature', 'webview-testing'),
      category: 'feature',
      title: 'WebView Integration testen',
      whyUseful: 'Android + WebView funktioniert am besten mit Tests.',
      affectedFiles: structure.androidFiles.slice(0, 3),
      risk: 'niedrig',
      expectedBenefit: 'WebView-Inhalte werden zuverlässig angezeigt.',
      actionLabel: 'WebView-Tests hinzufügen',
      priority: priority++,
    });
  }

  // Has components but limited tests
  if (structure.hasComponents && structure.testFiles.length < structure.componentFiles.length * 0.5) {
    suggestions.push({
      id: generateId('feature', 'component-coverage'),
      category: 'feature',
      title: 'Mehr Komponenten-Tests',
      whyUseful: 'UI-Komponenten sollten getestet werden.',
      affectedFiles: structure.componentFiles.slice(0, 5),
      risk: 'niedrig',
      expectedBenefit: 'UI bleibt auch bei Änderungen korrekt.',
      actionLabel: 'Component-Tests hinzufügen',
      priority: priority++,
    });
  }

  // Has runtime but no telemetry integration
  if (structure.hasRuntime && !structure.runtimeFiles.some((f) => f.includes('telemetry'))) {
    suggestions.push({
      id: generateId('feature', 'telemetry-integration'),
      category: 'feature',
      title: 'Telemetrie-Integration',
      whyUseful: 'Ohne Telemetrie sieht man nicht, was in der App passiert.',
      affectedFiles: structure.runtimeFiles.slice(0, 3),
      risk: 'niedrig',
      expectedBenefit: 'Bessere Einblicke in die App-Nutzung.',
      actionLabel: 'Telemetrie einbauen',
      priority: priority++,
    });
  }

  // Has config files but limited monitoring
  if (structure.configFiles.length > 0 && !structure.runtimeFiles.some((f) => f.includes('health'))) {
    suggestions.push({
      id: generateId('feature', 'health-monitoring'),
      category: 'feature',
      title: 'Gesundheits-Checks hinzufügen',
      whyUseful: 'Health-Checks zeigen, ob alles funktioniert.',
      affectedFiles: structure.configFiles.slice(0, 2),
      risk: 'niedrig',
      expectedBenefit: 'Schnellere Fehlererkennung.',
      actionLabel: 'Health-Checks einbauen',
      priority: priority++,
    });
  }

  return suggestions;
}

// ============================================================================
// Recommended Mission Generator
// ============================================================================

function generateRecommendedMission(
  structure: RepoStructureAnalysis,
  fixSuggestions: RepoInsightSuggestion[],
  hardeningSuggestions: RepoInsightSuggestion[],
  featureSuggestions: RepoInsightSuggestion[],
  currentMission: string,
): { mission: string; confidence: number } {
  // If user gave specific mission, respect it with low confidence boost
  if (!isPlaceholderMission(currentMission)) {
    return { mission: currentMission, confidence: 0.8 };
  }

  // Generate concrete mission from analysis
  const allSuggestions = [
    ...fixSuggestions.map((s) => ({ ...s, score: 100 - s.priority })),
    ...hardeningSuggestions.map((s) => ({ ...s, score: 80 - s.priority })),
    ...featureSuggestions.map((s) => ({ ...s, score: 50 - s.priority })),
  ].sort((a, b) => b.score - a.score);

  if (allSuggestions.length === 0) {
    return {
      mission: `Stabilisiere die Repository-Grundlagen: Füge README und grundlegende Tests hinzu.`,
      confidence: 0.7,
    };
  }

  // Pick the highest priority suggestion
  const topSuggestion = allSuggestions[0];

  // Build a beginner-friendly mission
  let mission = '';

  if (topSuggestion.category === 'fix') {
    const affectedFiles = topSuggestion.affectedFiles.slice(0, 2).join(', ');
    mission = `Repariere ${topSuggestion.title} in ${affectedFiles}`;
  } else if (topSuggestion.category === 'stabilitaet') {
    const affectedFiles = topSuggestion.affectedFiles.slice(0, 2).join(', ');
    mission = `Stabilisiere die App durch ${topSuggestion.title} (${affectedFiles})`;
  } else {
    const affectedFiles = topSuggestion.affectedFiles.slice(0, 2).join(', ');
    mission = `Erweitere das Projekt mit ${topSuggestion.title} in ${affectedFiles}`;
  }

  return {
    mission: mission.length > 120 ? mission.slice(0, 117) + '...' : mission,
    confidence: 0.85,
  };
}

// ============================================================================
// Coach Status Generator
// ============================================================================

function generateCoachStatus(
  fixSuggestions: RepoInsightSuggestion[],
  hardeningSuggestions: RepoInsightSuggestion[],
  blockers: RepoInsightBlocker[],
  isPlaceholder: boolean,
): { status: 'green' | 'yellow' | 'red'; message: string } {
  // Real blockers = red
  if (blockers.length > 0) {
    return {
      status: 'red',
      message: `⚠️ ${blockers[0].message}`,
    };
  }

  // Placeholder mission without repo = yellow
  if (isPlaceholder && fixSuggestions.length === 0 && hardeningSuggestions.length === 0) {
    return {
      status: 'yellow',
      message: 'Ich habe noch keinen konkreten Wunsch erkannt. Ich habe dir passende Vorschläge aus der Repo-Analyse erzeugt.',
    };
  }

  // Has suggestions from analysis = green
  if (fixSuggestions.length > 0 || hardeningSuggestions.length > 0) {
    return {
      status: 'green',
      message: 'Ich habe aus der Repo-Analyse eine sichere nächste Aufgabe erstellt.',
    };
  }

  // Default
  return {
    status: 'green',
    message: 'Repo ist analysiert. Wähle einen Vorschlag oder gib einen eigenen Auftrag.',
  };
}

// ============================================================================
// Blockers Detection
// ============================================================================

function detectBlockers(
  scanFindings: ScanFinding[],
  workflowReport: WorkflowWatchReport | null,
  repoFiles: RepoFile[],
): RepoInsightBlocker[] {
  const blockers: RepoInsightBlocker[] = [];

  // No repo loaded
  if (repoFiles.length === 0) {
    blockers.push({
      type: 'no-repo',
      message: 'Noch kein Repository geladen. Lade zuerst ein Repo.',
    });
    return blockers;
  }

  // Critical scan findings
  const criticalFindings = scanFindings.filter(
    (f) => f.severity === 'critical' || f.category === 'security-leak' || f.category === 'auth',
  );
  if (criticalFindings.length > 0) {
    blockers.push({
      type: 'critical-finding',
      message: `${criticalFindings.length} kritische(s) Problem(e) müssen zuerst behoben werden.`,
    });
  }

  // Failed CI checks
  if (workflowReport?.checks) {
    const failedChecks = workflowReport.checks.filter((c) => c.status === 'red');
    if (failedChecks.length > 0) {
      blockers.push({
        type: 'ci-failure',
        message: `${failedChecks.length} CI-Check(s) sind fehlgeschlagen. Repariere sie zuerst.`,
      });
    }
  }

  return blockers;
}

// ============================================================================
// Main Engine Function
// ============================================================================

export interface RepoInsightEngineResult {
  ok: boolean;
  output: RepoInsightEngineOutput | null;
  error: string | null;
}

/**
 * Create repo insight suggestions from real runtime sources.
 *
 * This function analyzes the repository structure and generates:
 * - Fix suggestions (from high severity findings and failures)
 * - Hardening suggestions (from runtime gaps and missing tests)
 * - Feature suggestions (from successful patterns and existing modules)
 * - Recommended mission (concrete next step for placeholder inputs)
 *
 * All suggestions are beginner-friendly:
 * - Short title
 * - Why it's useful
 * - Affected files
 * - Risk level
 * - Expected benefit
 * - Action button label
 */
export function createRepoInsightSuggestions(
  input: RepoInsightEngineInput,
): RepoInsightEngineResult {
  const { repoFiles, scanRegistry, workflowReport, telemetry, solutionPatternStore, currentMission = '' } = input;

  // Basic validation
  if (!repoFiles || repoFiles.length === 0) {
    return {
      ok: false,
      output: null,
      error: 'No repository files provided for analysis.',
    };
  }

  try {
    // Deep structure analysis
    const structure = analyzeRepoStructure(repoFiles);

    // Extract findings from registry
    const findings: ScanFinding[] = scanRegistry?.findings ?? [];
    const activeFindings = findings.filter((f) => f.status === 'active');

    // Detect blockers
    const blockers = detectBlockers(activeFindings, workflowReport ?? null, repoFiles);

    // Generate pattern matches from learned solution patterns (Hebbian-style learning)
    // Pass the pre-computed extension record to avoid re-parsing file extensions for all repoFiles.
    const patternMatches = generatePatternMatches(solutionPatternStore, repoFiles, structure.byExtension);

    // Generate suggestion groups
    const fixSuggestions = generateFixSuggestions(structure, activeFindings, workflowReport ?? null);
    const hardeningSuggestions = generateHardeningSuggestions(structure, activeFindings);
    const featureSuggestions = generateFeatureSuggestions(structure, patternMatches);

    // Generate recommended mission
    const { mission, confidence } = generateRecommendedMission(
      structure,
      fixSuggestions,
      hardeningSuggestions,
      featureSuggestions,
      currentMission,
    );

    // Generate coach status
    const isPlaceholder = isPlaceholderMission(currentMission);
    const { status: coachStatus, message: coachMessage } = generateCoachStatus(
      fixSuggestions,
      hardeningSuggestions,
      blockers,
      isPlaceholder,
    );

    // Calculate overall confidence
    const findingConfidence = Math.min(1, activeFindings.length / 10);
    const patternConfidence = Math.min(1, (solutionPatternStore?.patterns.length ?? 0) / 5);
    const overallConfidence = Math.min(0.95, (findingConfidence * 0.4 + patternConfidence * 0.3 + confidence * 0.3));

    // Build findings list for transparency
    const insightFindings: RepoInsightFinding[] = [];
    if (structure.missingReadme) insightFindings.push({ type: 'missing', path: 'README.md', description: 'README fehlt' });
    if (structure.missingTests) insightFindings.push({ type: 'missing', path: 'tests/', description: 'Keine Tests gefunden' });
    if (structure.missingWorkflows) insightFindings.push({ type: 'missing', path: '.github/workflows/', description: 'Keine CI/CD Workflows' });
    if (structure.hasRuntime) insightFindings.push({ type: 'detected', path: 'runtime/', description: `${structure.runtimeFiles.length} Runtime-Module` });
    if (structure.hasAndroid) insightFindings.push({ type: 'detected', path: 'android/', description: `${structure.androidFiles.length} Android-Dateien` });
    if (structure.hasComponents) insightFindings.push({ type: 'detected', path: 'components/', description: `${structure.componentFiles.length} Komponenten` });
    if (patternMatches.length > 0) {
      const topPattern = patternMatches[0].pattern;
      insightFindings.push({ type: 'pattern', path: topPattern.filePathHint, description: `${patternMatches.length} Pattern(s) matched, top: ${topPattern.problemSummary.slice(0, 50)}` });
    }

    return {
      ok: true,
      output: {
        fixSuggestions,
        hardeningSuggestions,
        featureSuggestions,
        recommendedMission: mission,
        recommendedMissionConfidence: confidence,
        confidence: overallConfidence,
        blockers,
        coachStatus,
        coachMessage,
        analyzedFiles: repoFiles.length,
        findings: insightFindings,
      },
      error: null,
    };
  } catch (error) {
    return {
      ok: false,
      output: null,
      error: error instanceof Error ? error.message : 'Unknown error in repo insight engine.',
    };
  }
}

// ============================================================================
// Utility Functions
// ============================================================================

export function getInsightGroups(output: RepoInsightEngineOutput): RepoInsightGroup[] {
  return [
    { category: 'fix', label: 'Fehler & Fixes', suggestions: output.fixSuggestions },
    { category: 'stabilitaet', label: 'Stabilität & Runtime', suggestions: output.hardeningSuggestions },
    { category: 'feature', label: 'Feature-Ideen', suggestions: output.featureSuggestions },
  ];
}

export function getHighestPrioritySuggestion(output: RepoInsightEngineOutput): RepoInsightSuggestion | null {
  const all = [
    ...output.fixSuggestions,
    ...output.hardeningSuggestions,
    ...output.featureSuggestions,
  ];
  if (all.length === 0) return null;
  return all.sort((a, b) => a.priority - b.priority)[0];
}

export function hasRealBlockers(output: RepoInsightEngineOutput): boolean {
  return output.blockers.some((b) => b.type !== 'no-repo' || output.analyzedFiles > 0);
}

export function canGenerateMission(output: RepoInsightEngineOutput): boolean {
  return !hasRealBlockers(output) && output.recommendedMissionConfidence >= 0.7;
}
