"""Read one owner-reported job and its queue selection without executing work."""
from __future__ import annotations

import collections
import json
import re
import subprocess
import sys

JOB_ID = sys.argv[1]
EXPECTED_REVISION = sys.argv[2]
if not re.fullmatch(r"agent-[0-9a-f]{32}", JOB_ID):
    raise SystemExit("invalid diagnostic job identity")
if not re.fullmatch(r"[0-9a-f]{40}", EXPECTED_REVISION):
    raise SystemExit("invalid diagnostic source revision")

INNER = r'''
import datetime, hashlib, json, os, re, subprocess
from pathlib import Path
import psycopg2
import psycopg2.extras
from agent_runtime.job_store import list_reconcilable_repository_jobs
from agent_runtime.workspace_policy import repo_dir_for_workspace

job_id = os.environ['SOVEREIGN_DIAGNOSTIC_JOB_ID']
report = {'jobId': job_id, 'runtimeRevision': os.environ.get('SOVEREIGN_SOURCE_REVISION'),
          'mutationPerformed': False, 'secretValuesReturned': False}
conn = psycopg2.connect(host=os.getenv('POSTGRES_HOST','db'),
    port=int(os.getenv('POSTGRES_PORT','5432')), dbname=os.getenv('POSTGRES_DB','postgres'),
    user=os.getenv('POSTGRES_USER','postgres'), password=os.getenv('POSTGRES_PASSWORD',''),
    connect_timeout=5, cursor_factory=psycopg2.extras.RealDictCursor,
    options='-c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=2000')
try:
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM sovereign_agent_jobs WHERE job_id = %s LIMIT 1', (job_id,))
        job = cur.fetchone()
    if job:
        ref = str(job.get('external_ref') or '')
        ref_class = ('pending-submit' if ref.startswith('sovereign-local-runner:pending:submit:')
            else 'submit-claim' if ref.startswith('sovereign-local-runner:claim:submit:')
            else 'closeout-claim' if ref.startswith('sovereign-local-runner:claim:closeout:')
            else 'bound' if ref.startswith('sovereign-local-runner:') else 'unbound-or-other')
        now = datetime.datetime.now(datetime.timezone.utc)
        report['job'] = {'status': job.get('status'), 'executor': job.get('executor'),
            'externalRefClass': ref_class, 'changedFileCount': len(job.get('changed_files') or []),
            'blockerPresent': bool(job.get('blocker')), 'prUrlPresent': bool(job.get('pr_url')),
            'createdAt': str(job.get('created_at')), 'updatedAt': str(job.get('updated_at')),
            'ageSeconds': int((now-job['created_at']).total_seconds()),
            'events': []}
        with conn.cursor() as cur:
            cur.execute('SELECT stage, level, created_at FROM sovereign_agent_events WHERE job_id=%s ORDER BY created_at DESC, id DESC LIMIT 40', (job_id,))
            report['job']['events'] = [{'stage': row['stage'], 'level': row['level'],
                'at': str(row['created_at'])} for row in cur.fetchall()]
        root = Path(os.getenv('SOVEREIGN_AGENT_WORKSPACE_ROOT','/var/lib/sovereign-agent/workspaces'))
        repository = repo_dir_for_workspace(str(job.get('workspace_id') or job_id), root)
        report['workspace'] = {'repositoryPresent': repository.is_dir(),
            'gitPresent': (repository/'.git').is_dir(), 'testFilePresent': False}
        if repository.is_dir() and (repository/'.git').is_dir():
            result = subprocess.run(['git','--no-optional-locks','-C',str(repository),'status','--porcelain','-z'], capture_output=True, timeout=10)
            report['workspace']['gitStatusExitCode'] = result.returncode
            report['workspace']['changedRecordCount'] = len([v for v in result.stdout.split(b'\0') if v])
            candidate = repository/'Testgb'
            if candidate.is_file() and not candidate.is_symlink() and candidate.stat().st_size <= 32:
                data = candidate.read_bytes()
                report['workspace'].update({'testFilePresent': True, 'testFileBytes': len(data),
                    'testFileContentMatches': data.rstrip(b'\r\n') == b'1987a26',
                    'testFileSha256': hashlib.sha256(data).hexdigest()})
    else:
        report['job'] = {'present': False}
    try:
        candidates = list_reconcilable_repository_jobs(conn, limit=50)
        report['queue'] = {'selectionSucceeded': True, 'selectedCount': len(candidates),
            'targetSelected': any(row.job_id == job_id for row in candidates),
            'targetPosition': next((i for i,row in enumerate(candidates) if row.job_id==job_id),None)}
    except Exception as exc:
        report['queue'] = {'selectionSucceeded': False, 'errorType': type(exc).__name__,
            'sqlState': getattr(exc,'pgcode',None)}
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT state, wait_event_type, wait_event, count(*) AS count FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() GROUP BY state, wait_event_type, wait_event")
        report['databaseActivity'] = [dict(row) for row in cur.fetchall()]
finally:
    conn.close()
print(json.dumps(report, sort_keys=True))
'''

def run(argv: list[str], *, data: str | None = None, timeout: int = 45):
    return subprocess.run(argv, input=data, capture_output=True, text=True, timeout=timeout, check=False)

report = {"schemaVersion": "sovereign.repository-queue-diagnostic.v1", "jobId": JOB_ID,
          "expectedRevision": EXPECTED_REVISION, "mutationPerformed": False, "secretValuesReturned": False}
inspected = run(["docker", "inspect", "sovereign-backend"])
if inspected.returncode != 0:
    raise SystemExit("backend container inspection failed")
container = json.loads(inspected.stdout)[0]
labels = container.get("Config", {}).get("Labels", {}) or {}
report["backend"] = {"revision": labels.get("org.opencontainers.image.revision"),
    "status": container.get("State", {}).get("Status"),
    "health": container.get("State", {}).get("Health", {}).get("Status"),
    "restartCount": container.get("RestartCount"),
    "productionBootstrapConfigured": "production_app:app" in " ".join(container.get("Config",{}).get("Cmd",[]) or [])}
logs = run(["docker", "logs", "--since", "30m", "--tail", "5000", "sovereign-backend"])
text = logs.stdout + logs.stderr
types = re.findall(r"repository local-runner reconcile(?: cycle)? failed(?: job=[a-z0-9-]+)? type=([A-Za-z_][A-Za-z0-9_]*)", text)
report["reconcilerLogErrorTypes"] = dict(collections.Counter(types))
target_types = re.findall(r"repository local-runner reconcile failed job="+re.escape(JOB_ID)+r" type=([A-Za-z_][A-Za-z0-9_]*)", text)
report["targetReconcilerLogErrorTypes"] = dict(collections.Counter(target_types))
readback = run(["docker", "exec", "-i", "-e", "SOVEREIGN_DIAGNOSTIC_JOB_ID="+JOB_ID,
    "sovereign-backend", "python3", "-"], data=INNER)
report["readbackExitCode"] = readback.returncode
if readback.returncode == 0:
    report["readback"] = json.loads(readback.stdout)
else:
    report["readbackErrorClasses"] = re.findall(r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):.*$", readback.stderr, re.M)[-3:]
print(json.dumps(report, sort_keys=True))
raise SystemExit(0 if readback.returncode == 0 else 1)
