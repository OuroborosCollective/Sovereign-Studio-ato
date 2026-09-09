import { mkdirSync, writeFileSync } from 'node:fs';
import type { FullResult, Reporter, TestCase, TestError, TestResult, TestStep } from '@playwright/test/reporter';

/** Metadata-only live reporting: never serialize Playwright steps, error bodies or credential input. */
export function safeFailure(error: Pick<TestError, 'message' | 'stack'>): { family: string; line: number | null } {
  const message = String(error.message || '');
  const http = message.match(/\bLIVE_(AUTH|SESSION)_HTTP_([1-5][0-9]{2})\b/);
  const known = [
    'LIVE_AUTH_ACCOUNT_ID_MISSING', 'LIVE_AUTH_ISSUED_ACCOUNT_MISMATCH',
    'LIVE_AUTH_AGENT_ORIGIN_MISMATCH', 'LIVE_SESSION_RESPONSE_INVALID',
    'LIVE_SESSION_ACCOUNT_MISMATCH', 'LIVE_SESSION_AUTHENTICATED_IDENTITY_REQUIRED',
    'LIVE_SESSION_CREDIT_READBACK_UNVERIFIED',
  ].find(code => message.includes(code));
  const family = http ? `LIVE_${http[1]}_HTTP_${http[2]}` : known
    || (message.includes('beforeAll') && message.includes('timeout') ? 'SETUP_TIMEOUT'
      : message.includes('Expected exactly five') ? 'FIVE_DRAFT_PR_PROOF_INCOMPLETE'
      : message.includes('READY_TO_PUBLISH') ? 'PUBLICATION_GATE_NOT_REACHED'
      : message.includes('registration failed') ? 'ACCOUNT_REGISTRATION_FAILED'
      : message.includes('account-key issue failed') ? 'ACCOUNT_KEY_ISSUANCE_FAILED'
      : message.includes('Timeout') || message.includes('timeout') ? 'BOUNDED_TIMEOUT'
      : 'ASSERTION_OR_RUNTIME_FAILURE');
  const location = String(error.stack || '').match(/five-draft-pr-paths\.spec\.ts:(\d+):\d+/);
  return { family, line: location ? Number(location[1]) : null };
}

export function safeTestResult(test: Pick<TestCase, 'location'>, result: Pick<TestResult, 'status' | 'duration' | 'errors'>) {
  return {
    status: result.status,
    durationMs: result.duration,
    sourceLine: test.location.line,
    errors: result.errors.map(safeFailure),
  };
}

export default class LiveSafeReporter implements Reporter {
  private results: ReturnType<typeof safeTestResult>[] = [];
  private failures: ReturnType<typeof safeFailure>[] = [];
  private stdoutBytes = 0;
  private stderrBytes = 0;
  printsToStdio() { return true; }
  onStdOut(chunk: string | Buffer) { this.stdoutBytes += Buffer.byteLength(chunk); }
  onStdErr(chunk: string | Buffer) { this.stderrBytes += Buffer.byteLength(chunk); }
  onError(error: TestError) {
    const failure = safeFailure(error);
    this.failures.push(failure);
    console.log(JSON.stringify({ event: 'live_error', ...failure }));
  }
  onStepEnd(_test: TestCase, _result: TestResult, step: TestStep) {
    // Only known auth route names may leave the step tree. Fill arguments never do.
    const authRoute = step.title.match(/^(GET|POST|DELETE) "(\/api\/(?:auth\/(?:register|account-key|me)|security\/account-keys))"$/);
    if (authRoute) console.log(JSON.stringify({
      event: 'live_auth_request', method: authRoute[1], path: authRoute[2],
      durationMs: step.duration, failed: Boolean(step.error),
    }));
  }
  onTestEnd(test: TestCase, result: TestResult) {
    const projected = safeTestResult(test, result);
    this.results.push(projected);
    console.log(JSON.stringify({ event: 'live_test_result', ...projected }));
  }
  onEnd(result: FullResult): void {
    const report = {
      schema: 'sovereign.live-safe-reporter.v1',
      runId: process.env.GITHUB_RUN_ID || null,
      runAttempt: process.env.GITHUB_RUN_ATTEMPT || null,
      sourceRevision: process.env.SOVEREIGN_E2E_REVISION || null,
      status: result.status,
      tests: this.results,
      failures: this.failures,
      omittedWorkerOutputBytes: { stdout: this.stdoutBytes, stderr: this.stderrBytes },
      policy: 'metadata-only-no-step-titles-no-raw-errors-no-worker-streams',
    };
    mkdirSync('test-results', { recursive: true });
    writeFileSync('test-results/live-safe-reporter.json', `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    console.log(JSON.stringify({ event: 'live_suite_end', status: result.status, testCount: this.results.length }));
    // Deliberately return void: reporting must never override the actual test status.
  }
}
