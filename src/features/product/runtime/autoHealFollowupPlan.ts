import type { WorkflowWatchReport } from './workflowWatch';
import type { WorkflowJobEvidenceReport } from './workflowJobEvidence';
import { formatWorkflowEvidenceForRepair } from './workflowJobEvidence';

export interface AutoHealFollowupPlan {
  enabled: boolean;
  blocked: boolean;
  reason: string;
  mission: string;
  requiredGates: string[];
  evidenceSummary: string;
}

const REQUIRED_GATES = [
  'repo snapshot ready',
  'functional guards',
  'generated file review',
  'diff preview when available',
  'draft PR only',
  'workflow watch follow-up',
];

export function buildAutoHealFollowupPlan(report: WorkflowWatchReport | null, evidence: WorkflowJobEvidenceReport[] = []): AutoHealFollowupPlan {
  if (!report) {
    return { enabled: false, blocked: true, reason: 'No workflow report available.', mission: '', requiredGates: REQUIRED_GATES, evidenceSummary: '' };
  }
  if (report.status !== 'red') {
    return { enabled: false, blocked: true, reason: `Workflow status is ${report.status}; follow-up repair is not required.`, mission: '', requiredGates: REQUIRED_GATES, evidenceSummary: '' };
  }

  const evidenceSummary = evidence.map(formatWorkflowEvidenceForRepair).filter(Boolean).join('\n\n');
  const checkNames = report.checks.filter((check) => check.status === 'red').map((check) => check.name).join(', ') || 'failing checks';
  const mission = [
    `Prepare a focused repair package for: ${checkNames}.`,
    evidenceSummary ? `Evidence:\n${evidenceSummary}` : `Evidence:\n${report.summary}`,
    'Keep changes minimal and route the result through generated file review before any Draft PR.',
  ].join('\n\n');

  return {
    enabled: true,
    blocked: false,
    reason: 'Repair follow-up can be prepared as a reviewed package.',
    mission,
    requiredGates: REQUIRED_GATES,
    evidenceSummary: evidenceSummary || report.summary,
  };
}
