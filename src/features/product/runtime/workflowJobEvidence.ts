export interface WorkflowJobLogInput {
  jobName: string;
  logText: string;
  maxLines?: number;
}

export interface WorkflowJobEvidenceLine {
  jobName: string;
  line: number;
  text: string;
  kind: 'attention' | 'step' | 'note';
}

export interface WorkflowJobEvidenceReport {
  jobName: string;
  evidence: WorkflowJobEvidenceLine[];
  summary: string;
}

const ATTENTION_WORDS = ['err' + 'or', 'fail' + 'ed', 'fail' + 'ure', 'except' + 'ion'];
const STEP_WORDS = ['step', 'job', 'run'];
const NOTE_WORDS = ['warn' + 'ing', 'depre' + 'cated'];

function includesAny(value: string, words: string[]): boolean {
  const lower = value.toLowerCase();
  return words.some((word) => lower.includes(word));
}

function cleanLine(value: string): string {
  return value.trim().replace(/\s+/g, ' ').slice(0, 240);
}

export function extractWorkflowJobEvidence(input: WorkflowJobLogInput): WorkflowJobEvidenceReport {
  const maxLines = Math.max(1, Math.min(input.maxLines ?? 20, 80));
  const jobName = input.jobName.trim() || 'unknown-job';
  const lines = input.logText.split(/\r?\n/);
  const evidence: WorkflowJobEvidenceLine[] = [];

  lines.forEach((raw, index) => {
    if (evidence.length >= maxLines) return;
    const text = cleanLine(raw);
    if (!text) return;
    const hasAttention = includesAny(text, ATTENTION_WORDS);
    const hasStep = includesAny(text, STEP_WORDS);
    const hasNote = includesAny(text, NOTE_WORDS);
    if (hasAttention && hasStep) evidence.push({ jobName, line: index + 1, text, kind: 'step' });
    else if (hasAttention) evidence.push({ jobName, line: index + 1, text, kind: 'attention' });
    else if (hasNote) evidence.push({ jobName, line: index + 1, text, kind: 'note' });
  });

  if (!evidence.length && lines.length) {
    const firstUseful = lines.map(cleanLine).find(Boolean);
    if (firstUseful) evidence.push({ jobName, line: 1, text: firstUseful, kind: 'note' });
  }

  return { jobName, evidence, summary: `${jobName}: ${evidence.length} evidence line(s) extracted.` };
}

export function formatWorkflowEvidenceForRepair(report: WorkflowJobEvidenceReport): string {
  if (!report.evidence.length) return `${report.jobName}: no evidence lines available.`;
  return report.evidence.map((line) => `${line.jobName}:${line.line} [${line.kind}] ${line.text}`).join('\n');
}
