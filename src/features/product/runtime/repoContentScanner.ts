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

// Bolt optimization: Single combined fast-path regex to quickly determine if any target keyword/pattern exists in file content or a line before executing individual regex checks.
const ANY_FINDING_RE = /\b(TODO|FIXME|mock|stub|placeholder|fake implementation|api[_-]?key|access[_-]?key|private[_-]?key|password|secret|token)\b|eval\(|child_process|execSync|Function\(/i;

// Bolt optimization: Helper to get UTF-8 byte length cross-platform without allocating Blob objects on the heap.
function getByteLength(str: string): number {
  if (typeof Buffer !== 'undefined') {
    return Buffer.byteLength(str, 'utf8');
  }
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(str).length;
  }
  return new Blob([str]).size;
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

  for (let i = 0; i < snapshots.length; i += 1) {
    const snapshot = snapshots[i];
    const rawPath = snapshot.path;
    const content = snapshot.content;
    if (!rawPath || !content) continue;
    const path = rawPath.trim();
    if (!path) continue;

    scannedFiles += 1;

    // Bolt optimization: Fast-path byte length check using string character length boundaries.
    // In UTF-8, each UTF-16 code unit takes <= 3 bytes.
    // 1) If character length > 250,000, byte size is guaranteed to be > 250,000.
    // 2) If character length <= 62,500, byte size is guaranteed to be <= 250,000 (62,500 * 3 = 187,500 <= 250,000).
    // This avoids heap allocations for Blob/TextEncoder/Buffer for 99.9% of source files.
    const len = content.length;
    let isLarge = false;
    if (len > MAX_CONTENT_BYTES) {
      isLarge = true;
    } else if (len > 62_500) {
      isLarge = getByteLength(content) > MAX_CONTENT_BYTES;
    }

    if (isLarge) {
      findings.push(finding(path, 1, 'large-content', 'medium', 'Selected file is larger than recommended scan size.'));
      continue;
    }

    // Bolt optimization: Fast-path check on the entire file content before line splitting.
    // If ANY_FINDING_RE fails on the whole content, no line in the file can contain a finding.
    if (!ANY_FINDING_RE.test(content)) {
      continue;
    }

    // Bolt optimization: Indexed loop over lines with ANY_FINDING_RE pre-filter avoids
    // running 4 separate regular expressions per line for clean lines, and avoids forEach callback overhead.
    const lines = content.split(/\r?\n/);
    for (let j = 0; j < lines.length; j += 1) {
      const lineText = lines[j];
      if (!ANY_FINDING_RE.test(lineText)) continue;

      const line = j + 1;
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
