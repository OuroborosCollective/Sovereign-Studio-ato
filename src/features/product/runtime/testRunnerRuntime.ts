/** Real frontend client for the existing Sovereign workspace test tool. */
export type TestRunnerStatus = 'passed' | 'failed' | 'blocked' | 'error';
export type TestFramework = 'pytest' | 'jest' | 'vitest' | 'go_test' | 'cargo_test' | 'unknown';
export interface TestRunnerInput { readonly jobId: string; readonly backendBase: string; readonly framework?: string; readonly testPath?: string; readonly timeoutSeconds?: number; readonly verbose?: boolean; readonly fetcher?: typeof fetch; }
export interface TestRunnerCounts { readonly passed: number; readonly failed: number; readonly errors: number; readonly skipped: number; }
export interface TestRunnerResult { readonly status: TestRunnerStatus; readonly jobId: string; readonly framework: TestFramework; readonly output: string; readonly counts: TestRunnerCounts; readonly durationMs: number; readonly blocker: string; readonly hasRepairHint: boolean; readonly summary: string; }
const SIGNATURES: Record<TestFramework, readonly string[]> = { pytest: ['::test_', 'pytest', 'PASSED', 'FAILED'], jest: ['PASS ', 'FAIL ', 'Tests:', 'jest'], vitest: ['vitest', 'Test Files', 'Tests  ', '✓', '×'], go_test: ['--- PASS', '--- FAIL', 'ok  \t', 'FAIL\t', 'go test'], cargo_test: ['test result:', 'cargo test'], unknown: [] };
const FRAMEWORK_DETECTION_ORDER: readonly TestFramework[] = ['vitest', 'jest', 'go_test', 'cargo_test', 'pytest'];
export function detectFrameworkFromOutput(output: string): TestFramework { for (const framework of FRAMEWORK_DETECTION_ORDER) if (SIGNATURES[framework].some((value) => output.includes(value))) return framework; return 'unknown'; }
export function parseTestCounts(output: string): TestRunnerCounts {
  const count = (pattern: RegExp) => Number(output.match(pattern)?.[1] ?? 0);
  const passed = count(/(\d+)\s+passed/); const failed = count(/(\d+)\s+failed/); const errors = count(/(\d+)\s+error(?:s)?/); const skipped = count(/(\d+)\s+skipped/);
  if (passed || failed || errors || skipped) return { passed, failed, errors, skipped };
  const jest = output.match(/Tests:\s*(?:(\d+)\s+failed[^,]*,\s*)?(?:(\d+)\s+passed[^,]*,\s*)?(?:(\d+)\s+skipped[^,]*,\s*)?(\d+)\s+total/);
  if (jest) return { failed: Number(jest[1] ?? 0), passed: Number(jest[2] ?? 0), skipped: Number(jest[3] ?? 0), errors: 0 };
  const goPassed = (output.match(/--- PASS:/g) ?? []).length; const goFailed = (output.match(/--- FAIL:/g) ?? []).length;
  return { passed: goPassed, failed: goFailed, errors: 0, skipped: 0 };
}
function empty(jobId: string, status: TestRunnerStatus, blocker: string, durationMs = 0): TestRunnerResult { return { status, jobId, framework: 'unknown', output: '', counts: { passed: 0, failed: 0, errors: 0, skipped: 0 }, durationMs, blocker, hasRepairHint: false, summary: blocker }; }
export async function runTests(input: TestRunnerInput): Promise<TestRunnerResult> {
  const jobId = input.jobId.trim(); if (!jobId) return empty(input.jobId, 'blocked', 'Test runner blocked: no active agent job ID.');
  const start = Date.now(); let response: Response;
  try { response = await (input.fetcher ?? fetch)(`${input.backendBase.replace(/\/$/, '')}/api/user/agent/jobs/${encodeURIComponent(jobId)}/tools/test`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ ...(input.framework ? { framework: input.framework } : {}), ...(input.testPath ? { path: input.testPath } : {}), timeout: Math.min(Math.max(input.timeoutSeconds ?? 120, 10), 600), verbose: input.verbose ?? true }) }); }
  catch (error) { return empty(jobId, 'error', `Test runner network error: ${error instanceof Error ? error.message : String(error)}`, Date.now() - start); }
  let body: Record<string, unknown> = {}; try { body = await response.json() as Record<string, unknown>; } catch { body = {}; }
  const tool = typeof body.tool === 'object' && body.tool !== null ? body.tool as Record<string, unknown> : body;
  const toolStatus = String(tool.status ?? ''); const output = String(tool.stdout ?? tool.output ?? ''); const blocker = String(tool.blocker ?? body.blocker ?? body.error ?? ''); const exitCode = Number(tool.exitCode ?? tool.exit_code ?? 0); const durationMs = Date.now() - start;
  if (toolStatus === 'blocked' || response.status === 403 || response.status === 404) return { ...empty(jobId, 'blocked', blocker || 'Test runner blocked: workspace unavailable.', durationMs), output };
  if (toolStatus !== 'done' && toolStatus !== 'ok') return { ...empty(jobId, 'error', blocker || `Test runner error: HTTP ${response.status}.`, durationMs), output };
  const framework = input.framework && input.framework in SIGNATURES ? input.framework as TestFramework : detectFrameworkFromOutput(output); const counts = parseTestCounts(output); const failedRun = exitCode !== 0 || counts.failed > 0 || counts.errors > 0; const status: TestRunnerStatus = failedRun ? 'failed' : 'passed';
  const summary = failedRun ? `Tests failed${framework === 'unknown' ? '' : ` (${framework})`}: ${counts.failed} failed, ${counts.errors} errors, ${counts.passed} passed.` : counts.passed ? `All tests passed${framework === 'unknown' ? '' : ` (${framework})`}: ${counts.passed} passed${counts.skipped ? `, ${counts.skipped} skipped` : ''}.` : `Test run completed${framework === 'unknown' ? '' : ` (${framework})`}; no failing process exit was reported.`;
  return { status, jobId, framework, output, counts, durationMs, blocker: '', hasRepairHint: failedRun, summary };
}
