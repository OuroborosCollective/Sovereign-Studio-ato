import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const APP_PATH = 'src/App.tsx';
const AGENT_STREAM_PATH = 'src/features/product/components/AgentEventStream.tsx';
const ACTION_STRIP_PATH = 'src/features/product/components/ActionSuggestionStrip.tsx';
const CONSENT_CARD_PATH = 'src/features/product/components/IntegrationIntentDraftCard.tsx';

function read(path: string): string {
  expect(existsSync(path), `${path} must exist`).toBe(true);
  return readFileSync(path, 'utf8');
}

describe('DevChat consent and conversation flow contract', () => {
  it('never auto-adopts the latest persisted agent job into a fresh chat', () => {
    const app = read(APP_PATH);

    expect(app).not.toContain('agentClient.listJobs()');
    expect(app).not.toContain('restoreLatestJob');
    expect(app).toContain('const adoptRescueJob = async (jobId: string) =>');
    expect(app).toContain('onJobReady={adoptRescueJob}');
  });

  it('keeps detailed agent runtime evidence collapsed until the user asks for it', () => {
    const source = read(AGENT_STREAM_PATH);

    expect(source).toContain('const [expanded, setExpanded] = useState(false)');
    expect(source).toContain('data-expanded={expanded ? \'true\' : \'false\'}');
    expect(source).toContain("{expanded ? 'Details ausblenden' : 'Details'}");
    expect(source).toContain('{expanded && (');
  });

  it('keeps guided repo actions compact by default so the composer owns the bottom of chat', () => {
    const source = read(ACTION_STRIP_PATH);

    expect(source).toContain('const [expanded, setExpanded] = useState(false)');
    expect(source).toContain('aria-controls="sovereign-guided-actions"');
    expect(source).toContain('{expanded && (');
  });

  it('keeps rejection available even when execution confirmation is blocked', () => {
    const source = read(CONSENT_CARD_PATH);
    const rejectStart = source.indexOf('data-testid="btn-reject"');
    expect(rejectStart).toBeGreaterThan(0);

    const rejectArea = source.slice(Math.max(0, rejectStart - 500), rejectStart + 500);
    expect(rejectArea).not.toContain('disabled=');
    expect(rejectArea).toContain('onClick={onReject}');
    expect(source).toContain('data-enabled="true"');
    expect(source).toContain('Einbauen wartet:');
  });
});
