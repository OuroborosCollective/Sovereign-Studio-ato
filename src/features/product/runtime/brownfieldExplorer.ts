export type BrownfieldSeverity = 'critical' | 'warn' | 'info';

export type BrownfieldCategory =
  | 'naming'
  | 'test-coverage'
  | 'pattern-inconsistency'
  | 'dependency'
  | 'size'
  | 'tree-integrity';

export interface BrownfieldFinding {
  id: string;
  severity: BrownfieldSeverity;
  category: BrownfieldCategory;
  label: string;
  detail: string;
  file?: string;
  count?: number;
}

export interface BrownfieldScore {
  total: number;
  naming: number;
  testCoverage: number;
  patternHealth: number;
  dependency: number;
  size: number;
  treeIntegrity: number;
}

export interface BrownfieldReport {
  repoName: string;
  branch: string;
  analyzedAt: number;
  fileCount: number;
  sourceFileCount: number;
  testFileCount: number;
  score: BrownfieldScore;
  findings: BrownfieldFinding[];
  topHotspots: string[];
  summary: string;
  status: 'complete' | 'partial';
}

export interface BrownfieldExplorerInput {
  repoName: string;
  branch: string;
  files: string[];
  analyzedAt?: number;
}

const SOURCE_FILE_RE = /\.(?:ts|tsx|js|jsx)$/i;
const TEST_FILE_RE = /(?:^|\/)(?:__tests__|tests)\/|\.(?:test|spec)\.(?:ts|tsx|js|jsx)$/i;
const LOCKFILE_RE = /^(?:pnpm-lock\.yaml|package-lock\.json|yarn\.lock|bun\.lockb)$/i;

const LEGACY_PATH_RE = /(?:^|[\/._-])(?:legacy|old|backup|deprecated|unused|archive|draft|wip|temp|tmp|copy)(?:[\/._-]|$)/i;

const STATE_PATTERN_MARKERS: Array<{ id: string; re: RegExp; label: string }> = [
  { id: 'zustand', re: /(?:^|[\/._-])zustand(?:[\/._-]|$)/i, label: 'Zustand' },
  { id: 'redux', re: /(?:^|\/)(?:redux|.+\.slice\.(?:ts|tsx|js|jsx)$)/i, label: 'Redux/Slices' },
  { id: 'jotai', re: /(?:^|\/|\.|-|_)atom(?:\.|-|_|\/)/i, label: 'Jotai/Atoms' },
  { id: 'recoil', re: /(?:^|\/)recoil(?:\/|\.|-|_)/i, label: 'Recoil' },
  { id: 'mobx', re: /(?:^|\/)mobx(?:\/|\.|-|_)/i, label: 'MobX' },
];

function normalizeName(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

function normalizeTimestamp(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.floor(value) : 0;
}

function normalizeFilePath(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim().replace(/\\/g, '/').replace(/^\.\//, '');
  if (!trimmed || trimmed.startsWith('/') || trimmed.includes('\u0000')) return null;
  return trimmed;
}

function uniqueNormalizedFiles(files: unknown): string[] {
  if (!Array.isArray(files)) return [];
  const seen = new Set<string>();
  const normalized: string[] = [];
  for (const value of files) {
    const path = normalizeFilePath(value);
    if (!path || seen.has(path)) continue;
    seen.add(path);
    normalized.push(path);
  }
  // Bolt ⚡ Optimization:
  // Native V8 fast sort is lexicographical by default when no comparator is passed,
  // which is extremely fast (up to 10-20x faster) and avoids slow localeCompare overhead.
  return normalized.sort();
}

function isSourceFile(path: string): boolean {
  return SOURCE_FILE_RE.test(path) && !TEST_FILE_RE.test(path);
}

function isTestFile(path: string): boolean {
  return TEST_FILE_RE.test(path);
}

function severityWeight(severity: BrownfieldSeverity): number {
  if (severity === 'critical') return 10;
  if (severity === 'warn') return 4;
  return 1;
}

function scoreFor(findings: BrownfieldFinding[], category: BrownfieldCategory, maxWeight: number): number {
  const weight = findings
    .filter((finding) => finding.category === category)
    .reduce((total, finding) => total + severityWeight(finding.severity), 0);
  return Math.min(100, Math.round((weight / maxWeight) * 100));
}

function categoryScore(findings: BrownfieldFinding[]): BrownfieldScore {
  const naming = scoreFor(findings, 'naming', 24);
  const testCoverage = scoreFor(findings, 'test-coverage', 20);
  const patternHealth = scoreFor(findings, 'pattern-inconsistency', 16);
  const dependency = scoreFor(findings, 'dependency', 12);
  const size = scoreFor(findings, 'size', 30);
  const treeIntegrity = scoreFor(findings, 'tree-integrity', 20);
  const total = Math.round((naming + testCoverage + patternHealth + dependency + size + treeIntegrity) / 6);
  return { total, naming, testCoverage, patternHealth, dependency, size, treeIntegrity };
}

function directoryKey(path: string): string {
  const parts = path.split('/');
  if (parts.length <= 1) return '.';
  if (parts[0] === 'src' && parts.length >= 3) return parts.slice(0, 3).join('/');
  return parts.slice(0, 2).join('/');
}

function addLegacyNameFindings(legacyFiles: string[], findings: BrownfieldFinding[]): void {
  for (const file of legacyFiles.slice(0, 10)) {
    findings.push({
      id: `naming:${file}`,
      severity: 'warn',
      category: 'naming',
      label: 'Legacy-Dateiname',
      detail: 'Der Pfad wirkt wie veralteter, temporärer oder archivierter Code.',
      file,
    });
  }
  if (legacyFiles.length > 10) {
    findings.push({
      id: 'naming:legacy-bulk',
      severity: 'info',
      category: 'naming',
      label: 'Viele Legacy-Dateinamen',
      detail: `${legacyFiles.length} Pfade enthalten Legacy-/Temp-/Backup-Signale.`,
      count: legacyFiles.length,
    });
  }
}

function addCoverageFindings(sourceFiles: string[], testFiles: string[], findings: BrownfieldFinding[]): void {
  if (sourceFiles.length === 0) {
    findings.push({
      id: 'tree:no-source-files',
      severity: 'critical',
      category: 'tree-integrity',
      label: 'Keine Source-Dateien erkannt',
      detail: 'Im geladenen Baum wurden keine TypeScript/JavaScript-Source-Dateien erkannt.',
    });
    return;
  }

  const testRatio = testFiles.length / Math.max(sourceFiles.length, 1);
  if (testRatio < 0.1) {
    findings.push({
      id: 'coverage:very-low',
      severity: 'critical',
      category: 'test-coverage',
      label: 'Sehr niedrige Testdichte',
      detail: `${testFiles.length} Test-Dateien für ${sourceFiles.length} Source-Dateien erkannt.`,
      count: testFiles.length,
    });
  } else if (testRatio < 0.25) {
    findings.push({
      id: 'coverage:low',
      severity: 'warn',
      category: 'test-coverage',
      label: 'Niedrige Testdichte',
      detail: `${testFiles.length} Test-Dateien für ${sourceFiles.length} Source-Dateien erkannt.`,
      count: testFiles.length,
    });
  }
}

function addStatePatternFindings(statePatternSeen: Uint8Array, findings: BrownfieldFinding[]): void {
  const detected: string[] = [];
  for (let m = 0; m < STATE_PATTERN_MARKERS.length; m++) {
    if (statePatternSeen[m] === 1) {
      detected.push(STATE_PATTERN_MARKERS[m].label);
    }
  }
  if (detected.length < 2) return;
  findings.push({
    id: 'pattern:mixed-state-management',
    severity: 'warn',
    category: 'pattern-inconsistency',
    label: 'Gemischte State-Patterns',
    detail: `Mehrere State-Management-Signale im Dateibaum erkannt: ${detected.join(' + ')}.`,
    count: detected.length,
  });
}

function addDirectorySizeFindings(counts: Map<string, number>, findings: BrownfieldFinding[]): void {
  for (const [dir, count] of Array.from(counts.entries()).sort((a, b) => b[1] - a[1])) {
    if (dir === '.') continue;
    if (count > 80) {
      findings.push({
        id: `size:directory:${dir}`,
        severity: 'warn',
        category: 'size',
        label: 'Sehr großes Verzeichnis',
        detail: `${dir} enthält ${count} Dateien. Das ist ein Kopplungs- und Navigationsrisiko.`,
        file: dir,
        count,
      });
    } else if (count > 40) {
      findings.push({
        id: `size:directory:${dir}`,
        severity: 'info',
        category: 'size',
        label: 'Großes Verzeichnis',
        detail: `${dir} enthält ${count} Dateien. Splitting prüfen, falls Änderungen dort langsam werden.`,
        file: dir,
        count,
      });
    }
  }
}

function addDependencyFindings(hasPackageJson: boolean, hasLockfile: boolean, findings: BrownfieldFinding[]): void {
  if (!hasPackageJson) {
    findings.push({
      id: 'dependency:no-package-json',
      severity: 'info',
      category: 'dependency',
      label: 'package.json nicht erkannt',
      detail: 'Der Dateibaum enthält kein package.json. Dependency-Risiken können nicht bewertet werden.',
    });
    return;
  }

  if (!hasLockfile) {
    findings.push({
      id: 'dependency:no-lockfile',
      severity: 'warn',
      category: 'dependency',
      label: 'Lockfile fehlt',
      detail: 'package.json ist vorhanden, aber kein npm/yarn/pnpm/bun Lockfile wurde erkannt.',
    });
  }
}

function deriveHotspots(findings: BrownfieldFinding[]): string[] {
  const weights = new Map<string, number>();
  for (const finding of findings) {
    if (!finding.file) continue;
    weights.set(finding.file, (weights.get(finding.file) ?? 0) + severityWeight(finding.severity));
  }
  return Array.from(weights.entries())
    // Performance optimized: Replace slow localeCompare with native lexicographical comparison for file names
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .slice(0, 5)
    .map(([file]) => file);
}

function buildBrownfieldSummary(score: BrownfieldScore, findings: BrownfieldFinding[]): string {
  const critical = findings.filter((finding) => finding.severity === 'critical').length;
  const warnings = findings.filter((finding) => finding.severity === 'warn').length;
  const quality = score.total < 25 ? 'stabil' : score.total < 55 ? 'prüfenswert' : 'riskant';
  return `Brownfield ${quality}: Debt Index ${score.total}/100 · ${critical} kritisch · ${warnings} Warnungen`;
}

export function buildBrownfieldReport(input: BrownfieldExplorerInput): BrownfieldReport {
  const repoName = normalizeName(input.repoName, 'unknown-repo');
  const branch = normalizeName(input.branch, 'main');
  const files = uniqueNormalizedFiles(input.files);

  const sourceFiles: string[] = [];
  const testFiles: string[] = [];
  const legacyFiles: string[] = [];
  const counts = new Map<string, number>();
  let hasPackageJson = false;
  let hasLockfile = false;

  // Track state pattern markers seen
  const statePatternSeen = new Uint8Array(STATE_PATTERN_MARKERS.length);

  for (let i = 0; i < files.length; i++) {
    const path = files[i];

    // Source vs Test files using existing checked functions to preserve encapsulation & avoid unused functions
    if (isTestFile(path)) {
      testFiles.push(path);
    } else if (isSourceFile(path)) {
      sourceFiles.push(path);
    }

    // Legacy files
    if (LEGACY_PATH_RE.test(path)) {
      legacyFiles.push(path);
    }

    // State patterns check: test each marker that we haven't seen yet
    for (let m = 0; m < STATE_PATTERN_MARKERS.length; m++) {
      if (statePatternSeen[m] === 0 && STATE_PATTERN_MARKERS[m].re.test(path)) {
        statePatternSeen[m] = 1;
      }
    }

    // Directory size
    const dir = directoryKey(path);
    counts.set(dir, (counts.get(dir) ?? 0) + 1);

    // Dependency files
    if (!hasPackageJson && path === 'package.json') {
      hasPackageJson = true;
    }
    if (!hasLockfile && LOCKFILE_RE.test(path)) {
      hasLockfile = true;
    }
  }

  const findings: BrownfieldFinding[] = [];

  if (files.length === 0) {
    findings.push({
      id: 'tree:empty-repo',
      severity: 'critical',
      category: 'tree-integrity',
      label: 'Leerer Repo-Baum',
      detail: 'Es wurden keine Dateien zur Analyse übergeben.',
    });
  }

  addLegacyNameFindings(legacyFiles, findings);
  addCoverageFindings(sourceFiles, testFiles, findings);
  addStatePatternFindings(statePatternSeen, findings);
  addDirectorySizeFindings(counts, findings);
  addDependencyFindings(hasPackageJson, hasLockfile, findings);

  const sortedFindings = findings.sort((a, b) => {
    const bySeverity = severityWeight(b.severity) - severityWeight(a.severity);
    // Performance optimized: Replace slow localeCompare with native lexicographical comparison for finding IDs
    return bySeverity || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  });
  const score = categoryScore(sortedFindings);

  return {
    repoName,
    branch,
    analyzedAt: normalizeTimestamp(input.analyzedAt),
    fileCount: files.length,
    sourceFileCount: sourceFiles.length,
    testFileCount: testFiles.length,
    score,
    findings: sortedFindings.slice(0, 50),
    topHotspots: deriveHotspots(sortedFindings),
    summary: buildBrownfieldSummary(score, sortedFindings),
    status: files.length > 0 && sourceFiles.length > 0 ? 'complete' : 'partial',
  };
}

export function assertBrownfieldReportValid(report: BrownfieldReport): void {
  if (!report.repoName.trim()) throw new Error('Brownfield report has no repo name.');
  if (!report.branch.trim()) throw new Error('Brownfield report has no branch.');
  if (report.fileCount < 0 || report.sourceFileCount < 0 || report.testFileCount < 0) {
    throw new Error('Brownfield report contains negative counters.');
  }
  if (report.findings.length > 50) throw new Error('Brownfield report exposes more than 50 findings.');
  if (report.score.total < 0 || report.score.total > 100) throw new Error('Brownfield score is outside 0..100.');
}
