from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    assert count == 1, f"{label}: expected one match, got {count}"
    return text.replace(old, new, 1)


store_paths = [
    Path('backend/agent_runtime/job_store.py'),
    Path('scripts/sovereign-backend/agent_runtime/job_store.py'),
]
assert store_paths[0].read_text('utf-8') == store_paths[1].read_text('utf-8'), 'job_store mirror drift before patch'
store_insert = r'''

_AGENT_ZERO_REPOSITORY_ADMISSION_LOCK_KEY = 7201236190078890170
_AGENT_ZERO_A2A_PREFIX = "agent-zero-a2a:"
_AGENT_ZERO_WAIT_PREFIX = "agent-zero-a2a:wait:"
_AGENT_ZERO_CLOSEOUT_CLAIM_PREFIX = "agent-zero-a2a:claim:closeout:"


def _safe_external_ref(value: str, *, field: str) -> str:
    normalized = sanitize_agent_text(str(value or ""), 240)
    if not normalized or normalized != str(value or "").strip():
        raise ValueError(f"{field} is invalid")
    return normalized


def _agent_zero_admission_busy(cur: Any, *, exclude_job_id: str | None = None) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM sovereign_agent_jobs
        WHERE status = 'running'
          AND (%s::text IS NULL OR job_id <> %s)
          AND external_ref LIKE %s
          AND external_ref NOT LIKE %s
          AND external_ref NOT LIKE %s
        LIMIT 1
        """,
        (
            exclude_job_id,
            exclude_job_id,
            f"{_AGENT_ZERO_A2A_PREFIX}%",
            f"{_AGENT_ZERO_WAIT_PREFIX}%",
            f"{_AGENT_ZERO_CLOSEOUT_CLAIM_PREFIX}%",
        ),
    )
    return cur.fetchone() is not None


def admit_or_queue_agent_zero_repository_job(
    conn: Any,
    *,
    job_id: str,
    expected_ref: str | None,
    claim_ref: str,
    wait_ref: str,
) -> str:
    """Atomically claim the single Agent Zero admission slot or durably queue the job."""

    safe_claim = _safe_external_ref(claim_ref, field="claim_ref")
    safe_wait = _safe_external_ref(wait_ref, field="wait_ref")
    safe_expected = _safe_external_ref(expected_ref, field="expected_ref") if expected_ref is not None else None
    outcome = "lost"
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_AGENT_ZERO_REPOSITORY_ADMISSION_LOCK_KEY,))
        busy = _agent_zero_admission_busy(cur, exclude_job_id=job_id)
        target_status = "queued" if busy else "running"
        target_ref = safe_wait if busy else safe_claim
        cur.execute(
            """
            UPDATE sovereign_agent_jobs
            SET status = %s,
                external_ref = %s,
                blocker = NULL
            WHERE job_id = %s
              AND status = 'running'
              AND external_ref IS NOT DISTINCT FROM %s
            RETURNING job_id
            """,
            (target_status, target_ref, job_id, safe_expected),
        )
        if cur.fetchone() is not None:
            outcome = "queued" if busy else "claimed"
    conn.commit()
    return outcome


def claim_next_queued_agent_zero_repository_job(
    conn: Any,
) -> tuple[StoredSovereignAgentJob, str] | None:
    """Claim exactly one oldest queued repository job when Agent Zero has no active Sovereign task."""

    claimed_row = None
    claim_ref = ""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_AGENT_ZERO_REPOSITORY_ADMISSION_LOCK_KEY,))
        if not _agent_zero_admission_busy(cur):
            cur.execute(
                """
                SELECT *
                FROM sovereign_agent_jobs
                WHERE status = 'queued'
                  AND external_ref LIKE %s
                ORDER BY created_at ASC, job_id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (f"{_AGENT_ZERO_WAIT_PREFIX}%",),
            )
            queued_row = cur.fetchone()
            if queued_row is not None:
                job_id = str(queued_row.get("job_id") or "")
                wait_ref = str(queued_row.get("external_ref") or "")
                claim_ref = f"agent-zero-a2a:claim:submit:queued:{__import__('uuid').uuid4().hex}"
                cur.execute(
                    """
                    UPDATE sovereign_agent_jobs
                    SET status = 'running',
                        external_ref = %s,
                        blocker = NULL
                    WHERE job_id = %s
                      AND status = 'queued'
                      AND external_ref = %s
                    RETURNING *
                    """,
                    (claim_ref, job_id, wait_ref),
                )
                claimed_row = cur.fetchone()
    conn.commit()
    if claimed_row is None:
        return None
    return stored_job_from_row(claimed_row), claim_ref
'''
for path in store_paths:
    text = path.read_text('utf-8')
    text = replace_once(text, 'import json\nfrom typing import Any, Mapping, Sequence\n', 'import json\nfrom typing import Any, Mapping, Sequence\n', f'{path}: import guard')
    text = replace_once(text, '\n\ndef mark_draft_pr_prepared(\n', store_insert + '\n\ndef mark_draft_pr_prepared(\n', f'{path}: admission helpers')
    path.write_text(text, 'utf-8')
assert store_paths[0].read_text('utf-8') == store_paths[1].read_text('utf-8'), 'job_store mirror drift after patch'

runtime_paths = [
    Path('backend/agent_runtime/repository_execution.py'),
    Path('scripts/sovereign-backend/agent_runtime/repository_execution.py'),
]
assert runtime_paths[0].read_text('utf-8') == runtime_paths[1].read_text('utf-8'), 'repository_execution mirror drift before patch'
for path in runtime_paths:
    text = path.read_text('utf-8')
    text = replace_once(
        text,
        '    append_agent_event,\n    compare_and_swap_agent_job_external_ref,\n    list_reconcilable_repository_jobs,\n',
        '    admit_or_queue_agent_zero_repository_job,\n    append_agent_event,\n    claim_next_queued_agent_zero_repository_job,\n    compare_and_swap_agent_job_external_ref,\n    list_reconcilable_repository_jobs,\n',
        f'{path}: imports',
    )
    text = replace_once(
        text,
        '_A2A_CLAIM_PREFIX: Final[str] = "agent-zero-a2a:claim:"\n',
        '_A2A_CLAIM_PREFIX: Final[str] = "agent-zero-a2a:claim:"\n_A2A_WAIT_PREFIX: Final[str] = "agent-zero-a2a:wait:"\n',
        f'{path}: wait prefix',
    )
    text = replace_once(
        text,
        'def _retry_ref(task_id: str) -> str:\n    return f"{_A2A_RETRY_PREFIX}{task_id}"\n\n\ndef _bound_task(external_ref: str) -> tuple[str, bool] | None:\n',
        'def _retry_ref(task_id: str) -> str:\n    return f"{_A2A_RETRY_PREFIX}{task_id}"\n\n\ndef _wait_ref(job_id: str) -> str:\n    return f"{_A2A_WAIT_PREFIX}{job_id}"\n\n\ndef _bound_task(external_ref: str) -> tuple[str, bool] | None:\n    if external_ref.startswith(_A2A_WAIT_PREFIX):\n        return None\n',
        f'{path}: wait ref',
    )
    old_start = '''    claim_ref = _claim("submit", job.job_id)\n    if not compare_and_swap_agent_job_external_ref(\n        conn,\n        job_id=job.job_id,\n        expected_ref=None,\n        new_ref=claim_ref,\n    ):\n        # Another caller already owns the external-effect boundary. Never submit.\n        return read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job\n    claimed = read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job\n    return _submit_after_claim(\n        conn,\n        job=claimed,\n        claim_ref=claim_ref,\n        retry=False,\n        a2a_client_factory=a2a_client_factory,\n    )\n'''
    new_start = '''    claim_ref = _claim("submit", job.job_id)\n    wait_ref = _wait_ref(job.job_id)\n    admission = admit_or_queue_agent_zero_repository_job(\n        conn,\n        job_id=job.job_id,\n        expected_ref=None,\n        claim_ref=claim_ref,\n        wait_ref=wait_ref,\n    )\n    current = read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job\n    if admission == "lost":\n        # Another caller already owns the external-effect boundary. Never submit.\n        return current\n    if admission == "queued":\n        append_agent_event(conn, job.job_id, SovereignAgentEvent(\n            stage="agent_zero_a2a_admission_queued",\n            level="info",\n            message="Agent Zero is executing another Sovereign repository task; this persisted job is queued without sending a duplicate A2A request.",\n        ))\n        return read_agent_job(conn, user_id=user_id, job_id=job.job_id) or current\n    return _submit_after_claim(\n        conn,\n        job=current,\n        claim_ref=claim_ref,\n        retry=False,\n        a2a_client_factory=a2a_client_factory,\n    )\n'''
    text = replace_once(text, old_start, new_start, f'{path}: start admission')
    old_sig = '''def reconcile_repository_jobs_once(\n    *,\n    get_connection: ConnectionFactory,\n    workspace_root: Path | None = None,\n    limit: int = 50,\n) -> dict[str, int]:\n'''
    new_sig = '''def reconcile_repository_jobs_once(\n    *,\n    get_connection: ConnectionFactory,\n    workspace_root: Path | None = None,\n    limit: int = 50,\n    a2a_client_factory: A2AClientFactory = AgentZeroA2AClient.from_env,\n) -> dict[str, int]:\n'''
    text = replace_once(text, old_sig, new_sig, f'{path}: reconcile signature')
    text = replace_once(
        text,
        '                workspace_root=workspace_root,\n            )\n            reconciled += 1\n',
        '                workspace_root=workspace_root,\n                a2a_client_factory=a2a_client_factory,\n            )\n            reconciled += 1\n',
        f'{path}: reconcile client factory',
    )
    old_return = '''        finally:\n            _close_reconciler_connection(conn)\n    return {\n        "scanned": len(candidates),\n        "reconciled": reconciled,\n        "transientFailures": transient_failures,\n        "unexpectedFailures": unexpected_failures,\n    }\n'''
    new_return = '''        finally:\n            _close_reconciler_connection(conn)\n\n    queued_dispatch = None\n    admission_conn = get_connection()\n    try:\n        queued_dispatch = claim_next_queued_agent_zero_repository_job(admission_conn)\n    except Exception as exc:\n        unexpected_failures += 1\n        _LOGGER.warning("repository A2A admission scan failed type=%s", type(exc).__name__)\n    finally:\n        _close_reconciler_connection(admission_conn)\n\n    if queued_dispatch is not None:\n        queued_job, queued_claim_ref = queued_dispatch\n        conn = get_connection()\n        try:\n            _submit_after_claim(\n                conn,\n                job=queued_job,\n                claim_ref=queued_claim_ref,\n                retry=False,\n                a2a_client_factory=a2a_client_factory,\n            )\n            reconciled += 1\n        except RepositoryExecutionTransientError:\n            transient_failures += 1\n        except Exception as exc:\n            unexpected_failures += 1\n            _LOGGER.warning(\n                "repository queued A2A submit failed job=%s type=%s",\n                queued_job.job_id,\n                type(exc).__name__,\n            )\n        finally:\n            _close_reconciler_connection(conn)\n\n    return {\n        "scanned": len(candidates) + (1 if queued_dispatch is not None else 0),\n        "reconciled": reconciled,\n        "transientFailures": transient_failures,\n        "unexpectedFailures": unexpected_failures,\n    }\n'''
    text = replace_once(text, old_return, new_return, f'{path}: queued dispatch')
    path.write_text(text, 'utf-8')
assert runtime_paths[0].read_text('utf-8') == runtime_paths[1].read_text('utf-8'), 'repository_execution mirror drift after patch'

tests = Path('backend/tests/test_repository_execution.py')
text = tests.read_text('utf-8')
text = replace_once(
    text,
    '    monkeypatch.setattr(repository_execution, "reconcile_repository_execution", reconcile)\n\n    summary = repository_execution.reconcile_repository_jobs_once(\n',
    '    monkeypatch.setattr(repository_execution, "reconcile_repository_execution", reconcile)\n    monkeypatch.setattr(repository_execution, "claim_next_queued_agent_zero_repository_job", lambda _conn: None)\n\n    summary = repository_execution.reconcile_repository_jobs_once(\n',
    'repository test existing reconciler',
)
text = replace_once(text, '    assert len(connections) == 2\n', '    assert len(connections) == 3\n', 'repository test connection count')
text += r'''


def test_start_queues_without_submitting_when_agent_zero_admission_is_busy(monkeypatch):
    state = _patch_job_store(monkeypatch, _job(external_ref=None, status="running"))
    monkeypatch.setattr(
        repository_execution,
        "create_sovereign_agent_job",
        lambda *_args, **_kwargs: SimpleNamespace(job_id="agent-test"),
    )

    def admit(_conn, *, job_id, expected_ref, claim_ref, wait_ref):
        assert job_id == "agent-test"
        assert expected_ref is None
        assert claim_ref.startswith("agent-zero-a2a:claim:submit:")
        assert wait_ref == "agent-zero-a2a:wait:agent-test"
        state["job"] = replace(state["job"], status="queued", external_ref=wait_ref)
        return "queued"

    monkeypatch.setattr(repository_execution, "admit_or_queue_agent_zero_repository_job", admit)

    class Client:
        def submit_repository_task(self, **_kwargs):
            raise AssertionError("queued admission must not call Agent Zero")

    result = repository_execution.start_repository_execution(
        object(),
        user_id="owner-test",
        body={
            "mode": "free",
            "agentMode": "single",
            "intentMode": "repository_execution",
            "repositoryUrl": "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
            "repositoryBranch": "main",
            "mission": "Implement one bounded repository change.",
        },
        a2a_client_factory=Client,
    )

    assert result.status == "queued"
    assert result.external_ref == "agent-zero-a2a:wait:agent-test"
    assert any(event.stage == "agent_zero_a2a_admission_queued" for event in state["events"])


def test_server_reconciler_dispatches_exactly_one_waiting_job(monkeypatch):
    queued_claim = "agent-zero-a2a:claim:submit:queued:test"
    queued_job = _job(external_ref=queued_claim, status="running")
    connections = []
    submitted = []

    class Conn:
        def __init__(self):
            self.closed = False
        def close(self):
            self.closed = True

    def factory():
        conn = Conn()
        connections.append(conn)
        return conn

    monkeypatch.setattr(repository_execution, "list_reconcilable_repository_jobs", lambda _conn, *, limit=50: ())
    monkeypatch.setattr(
        repository_execution,
        "claim_next_queued_agent_zero_repository_job",
        lambda _conn: (queued_job, queued_claim),
    )

    def submit(_conn, *, job, claim_ref, retry, a2a_client_factory):
        submitted.append((job.job_id, claim_ref, retry, a2a_client_factory))
        return job

    monkeypatch.setattr(repository_execution, "_submit_after_claim", submit)
    client_factory = lambda: object()

    summary = repository_execution.reconcile_repository_jobs_once(
        get_connection=factory,
        workspace_root=Path("/tmp/server-owned-reconcile"),
        a2a_client_factory=client_factory,
    )

    assert summary == {
        "scanned": 1,
        "reconciled": 1,
        "transientFailures": 0,
        "unexpectedFailures": 0,
    }
    assert submitted == [("agent-test", queued_claim, False, client_factory)]
    assert len(connections) == 3
    assert all(conn.closed for conn in connections)
'''
tests.write_text(text, 'utf-8')

contract = Path('backend/tests/test_repository_single_a2a_contract.py')
text = contract.read_text('utf-8')
text = replace_once(
    text,
    '    assert "external_ref IS NOT DISTINCT FROM %s" in store\n    assert "RETURNING job_id" in store\n',
    '    assert "external_ref IS NOT DISTINCT FROM %s" in store\n    assert "RETURNING job_id" in store\n    assert "pg_advisory_xact_lock" in store\n    assert "claim_next_queued_agent_zero_repository_job" in store\n',
    'single a2a contract store admission',
)
text = replace_once(
    text,
    '    assert \'"agent-zero-a2a:retry:"\' in runtime\n',
    '    assert \'"agent-zero-a2a:retry:"\' in runtime\n    assert \'"agent-zero-a2a:wait:"\' in runtime\n    assert "admit_or_queue_agent_zero_repository_job" in runtime\n',
    'single a2a contract runtime admission',
)
contract.write_text(text, 'utf-8')

spec = Path('tests/e2e/five-draft-pr-paths.spec.ts')
text = spec.read_text('utf-8')
text = replace_once(
    text,
    "const A2A_TASK_REF = /^agent-zero-a2a:(?:retry:)?[A-Za-z0-9._:-]{1,200}$/;\n",
    "const A2A_TASK_REF = /^agent-zero-a2a:(?:retry:)?[A-Za-z0-9._:-]{1,200}$/;\nconst A2A_WAIT_REF = /^agent-zero-a2a:wait:[A-Za-z0-9._:-]{1,200}$/;\n",
    'five-path wait pattern',
)
text = replace_once(
    text,
    "function requireA2ATaskRef(value: string | null | undefined, stage: string): string {\n  const ref = String(value || '');\n  if (!A2A_TASK_REF.test(ref) || ref.includes(':claim:')) throw new Error(`${stage}: persistent Agent Zero A2A task binding missing or transient`);\n  return ref;\n}\n",
    "function requireA2ATaskRef(value: string | null | undefined, stage: string): string {\n  const ref = String(value || '');\n  if (!A2A_TASK_REF.test(ref) || ref.includes(':claim:') || A2A_WAIT_REF.test(ref)) throw new Error(`${stage}: persistent Agent Zero A2A task binding missing or transient`);\n  return ref;\n}\n\nfunction requireA2AStartRef(value: string | null | undefined): string {\n  const ref = String(value || '');\n  if (ref.includes(':claim:') || (!A2A_TASK_REF.test(ref) && !A2A_WAIT_REF.test(ref))) {\n    throw new Error('repository.start: durable Agent Zero admission/task binding missing');\n  }\n  return ref;\n}\n",
    'five-path start ref helper',
)
text = replace_once(
    text,
    "  const startExternalRef = requireA2ATaskRef(start.externalRef, 'repository.start');\n",
    "  const startExternalRef = requireA2AStartRef(start.externalRef);\n",
    'five-path start use',
)
spec.write_text(text, 'utf-8')

verifier = Path('scripts/verify-five-draft-pr-runtime-evidence.mjs')
text = verifier.read_text('utf-8')
text = replace_once(
    text,
    "const a2aRefPattern = /^agent-zero-a2a:(?:retry:)?[A-Za-z0-9._:-]{1,200}$/;\n",
    "const a2aRefPattern = /^agent-zero-a2a:(?:retry:)?[A-Za-z0-9._:-]{1,200}$/;\nconst a2aWaitRefPattern = /^agent-zero-a2a:wait:[A-Za-z0-9._:-]{1,200}$/;\n",
    'verifier wait pattern',
)
text = replace_once(
    text,
    "const validA2ARef = (value) => {\n  const ref = String(value || '');\n  return a2aRefPattern.test(ref) && !ref.includes(':claim:');\n};\n",
    "const validA2ARef = (value) => {\n  const ref = String(value || '');\n  return a2aRefPattern.test(ref) && !ref.includes(':claim:') && !a2aWaitRefPattern.test(ref);\n};\nconst validA2AStartRef = (value) => {\n  const ref = String(value || '');\n  return !ref.includes(':claim:') && (validA2ARef(ref) || a2aWaitRefPattern.test(ref));\n};\n",
    'verifier start helper',
)
text = replace_once(
    text,
    "  if (!validA2ARef(start.externalRef)) fail(`${jobId}: initial Agent Zero A2A binding invalid`);\n",
    "  if (!validA2AStartRef(start.externalRef)) fail(`${jobId}: initial Agent Zero admission/task binding invalid`);\n",
    'verifier start check',
)
verifier.write_text(text, 'utf-8')

eye = Path('src/features/control-surface-vnext/components/CyborgOcularMatrix/CyborgOcularMatrix.tsx')
text = eye.read_text('utf-8')
text = replace_once(
    text,
    '    <div className="relative hidden sm:flex items-center gap-2 select-none" data-testid="vnext-cyborg-ocular-matrix"',
    '    <div className="relative flex items-center gap-1 sm:gap-2 select-none shrink-0" data-testid="vnext-cyborg-ocular-matrix"',
    'ocular mobile visibility',
)
text = replace_once(
    text,
    '      <div className="relative w-[88px] h-[48px] md:w-[112px] md:h-[58px] flex items-center justify-center overflow-visible">',
    '      <div className="relative w-[50px] h-[32px] sm:w-[88px] sm:h-[48px] md:w-[112px] md:h-[58px] flex items-center justify-center overflow-visible">',
    'ocular mobile size',
)
eye.write_text(text, 'utf-8')

app = Path('src/features/control-surface-vnext/App.tsx')
text = app.read_text('utf-8')
phase_effect = """  useEffect(() => {\n    if (job?.phase) dispatchFsm({ type: 'BACKEND_PHASE_UPDATE', payload: { phase: job.phase } });\n  }, [job?.phase]);\n"""
terminal_effect = phase_effect + """\n  useEffect(() => {\n    if (!job?.id || !['BLOCKED', 'FAILED', 'CANCELLED'].includes(job.phase)) return;\n    const reason = job.error?.message?.trim();\n    setMessages((current) => current.map((message) => {\n      if (message.id !== `accepted-${job.id}`) return message;\n      return {\n        ...message,\n        role: 'system',\n        sender: 'SYSTEM',\n        content: `RUN ${job.phase} :: [${job.id}].${reason ? `\\n${reason}` : ''}\\nNo automatic resubmit was performed. Runtime readback remains authoritative.`,\n        evidenceBadge: `${job.phase} READBACK`,\n        timestamp: new Date().toISOString(),\n      };\n    }));\n  }, [job?.error?.message, job?.id, job?.phase]);\n"""
text = replace_once(text, phase_effect, terminal_effect, 'terminal run chat projection')
app.write_text(text, 'utf-8')

architecture = Path('src/features/control-surface-vnext/components/Architecture/ArchitectureModal.tsx')
text = architecture.read_text('utf-8')
text = replace_once(
    text,
    "['POST', '/api/user/agent/repository/run', 'Persist a repository mission as one Sovereign job and exactly one bounded Agent Zero A2A task.'],",
    "['POST', '/api/user/agent/repository/run', 'Persist the repository mission/workspace; admission may queue, then exactly one bounded Agent Zero A2A task is submitted when the server-owned slot is free.'],",
    'architecture admission truth',
)
architecture.write_text(text, 'utf-8')

truth = Path('src/features/control-surface-vnext/controlSurfaceTruthContract.test.ts')
text = truth.read_text('utf-8')
text = replace_once(
    text,
    "    expect(eye).toContain('EFFECTS DECORATIVE · STATE READBACK');\n",
    "    expect(eye).toContain('EFFECTS DECORATIVE · STATE READBACK');\n    expect(eye).toContain('relative flex items-center');\n    expect(eye).not.toContain('relative hidden sm:flex');\n",
    'truth ocular contract',
)
text = replace_once(
    text,
    "    expect(workspace).toContain('This does not claim the repository is globally clean.');\n",
    "    expect(workspace).toContain('This does not claim the repository is globally clean.');\n    const surface = source('src/features/control-surface-vnext/App.tsx');\n    expect(surface).toContain('No automatic resubmit was performed. Runtime readback remains authoritative.');\n    expect(surface).toContain('evidenceBadge: `${job.phase} READBACK`');\n",
    'truth terminal run contract',
)
truth.write_text(text, 'utf-8')

browser = Path('tests/e2e/builder-container-smoke.spec.ts')
text = browser.read_text('utf-8')
text = replace_once(
    text,
    "    await expect(page.locator('[data-testid=\"mobile-bottom-nav\"]')).toBeVisible();\n",
    "    await expect(page.locator('[data-testid=\"mobile-bottom-nav\"]')).toBeVisible();\n    await expect(page.getByTestId('vnext-cyborg-ocular-matrix')).toBeVisible();\n",
    'mobile ocular browser smoke',
)
browser.write_text(text, 'utf-8')

assert runtime_paths[0].read_text('utf-8') == runtime_paths[1].read_text('utf-8')
assert store_paths[0].read_text('utf-8') == store_paths[1].read_text('utf-8')
