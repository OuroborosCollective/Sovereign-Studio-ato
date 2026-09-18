export type RepoContentFindingKind = 'todo' | 'placeholder' | 'sensitive-marker' | 'risky-import' | 'large-content';
export type RepoContentFindingSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface RepoContentSnapshot {
  path: string;
  content: string;
}

export interface RepoContentFinding {
  id: string;
  path: string;
  line: number;
  kind: RepoContentFindingKind;
  severity: RepoContentFindingSeverity;
  evidence: string;
  confidence: 'content-scanned';
}

export interface RepoContentScanReport {
  scannedFiles: number;
  findings: RepoContentFinding[];
  summary: string;
}

const MAX_CONTENT_BYTES = 250_000;
const MAX_EVIDENCE = 180;
const TODO_RE = /\b(TODO|FIXME)\b/i;
const PLACEHOLDER_RE = /\b(mock|stub|placeholder|fake implementation)\b/i;
const SENSITIVE_RE = /\b(api[_-]?key|access[_-]?key|private[_-]?key|password|secret|token)\b\s*[:=]/i;
const RISKY_IMPORT_RE = /\b(eval\(|child_process|execSync|Function\()/;

// Hoisted TextEncoder instance to measure UTF-8 string byte length without Blob allocations.
const textEncoder = new TextEncoder();

/**
 * Checks whether content byte size exceeds MAX_CONTENT_BYTES without instantiating DOM Blob objects.
 * - If length > 250_000, UTF-8 byte count is guaranteed to exceed 250,000.
 * - If length <= 62_500, UTF-8 byte count is guaranteed to be <= 250,000.
 * - Otherwise, computes exact byte length via TextEncoder.
 */
function isOversized(content: string): boolean {
  if (content.length > MAX_CONTENT_BYTES) return true;
  if (content.length <= MAX_CONTENT_BYTES / 4) return false;
  return textEncoder.encode(content).length > MAX_CONTENT_BYTES;
}

function stableId(path: string, line: number, kind: string): string {
  let hash = 0x811c9dc5;
  const input = `${path}:${line}:${kind}`;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return `content-${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

function cleanEvidence(value: string): string {
  return value.trim().replace(/\s+/g, ' ').slice(0, MAX_EVIDENCE);
}

function finding(path: string, line: number, kind: RepoContentFindingKind, severity: RepoContentFindingSeverity, evidence: string): RepoContentFinding {
  return { id: stableId(path, line, kind), path, line, kind, severity, evidence: cleanEvidence(evidence), confidence: 'content-scanned' };
}

export function scanRepoContent(snapshots: RepoContentSnapshot[]): RepoContentScanReport {
  const findings: RepoContentFinding[] = [];
  let scannedFiles = 0;

  for (const snapshot of snapshots) {
    const path = snapshot.path.trim();
    const content = snapshot.content ?? '';
    if (!path || !content) continue;
    scannedFiles += 1;

    // Fast-path byte check eliminates DOM Blob creation
    if (isOversized(content)) {
      findings.push(finding(path, 1, 'large-content', 'medium', 'Selected file is larger than recommended scan size.'));
      continue;
    }

    const lines = content.split(/\r?\n/);
    const lineCount = lines.length;
    for (let index = 0; index < lineCount; index += 1) {
      const lineText = lines[index];
      const line = index + 1;
      if (SENSITIVE_RE.test(lineText)) findings.push(finding(path, line, 'sensitive-marker', 'critical', lineText));
      else if (RISKY_IMPORT_RE.test(lineText)) findings.push(finding(path, line, 'risky-import', 'high', lineText));
      else if (PLACEHOLDER_RE.test(lineText)) findings.push(finding(path, line, 'placeholder', 'medium', lineText));
      else if (TODO_RE.test(lineText)) findings.push(finding(path, line, 'todo', 'low', lineText));
    }
  }

  return {
    scannedFiles,
    findings,
    summary: `${snapshots.length} selected file(s), ${findings.length} content finding(s).`,
  };
}
