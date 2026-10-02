"""Real PostgreSQL regressions against the shipping migrations and store functions.

The CI service is disposable. This file never connects to the production database.
"""
from pathlib import Path
import os
import sys
import uuid

import pytest
import psycopg2
from psycopg2 import extras, sql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.agent_runtime.cognitive_run_store import (
    append_repository_executor_heartbeat, read_job_runtime_evidence, record_agent_stage_event,
)

OWNER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
JOB = "agent-postgres-regression"
RUN = f"repo-{JOB}"
CLAIM = "sovereign-local-runner:claim:submit:postgres-regression"


@pytest.fixture
def database():
    dsn = os.getenv("SOVEREIGN_RUNTIME_TEST_DSN")
    if not dsn:
        pytest.skip("Disposable PostgreSQL service is not configured locally; required in backend CI.")
    conn = psycopg2.connect(dsn, cursor_factory=extras.RealDictCursor, connect_timeout=5)
    schema = f"runtime_evidence_test_{uuid.uuid4().hex}"
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA {}" ).format(sql.Identifier(schema)))
        cur.execute(sql.SQL("SET search_path TO {}" ).format(sql.Identifier(schema)))
        cur.execute("CREATE TABLE admin_users (id UUID PRIMARY KEY)")
    conn.commit()
    for migration in ("003_sovereign_agent_jobs.sql", "018_agents_sdk_runtime_state.sql", "019_agents_sdk_resume_lease.sql"):
        with conn.cursor() as cur:
            cur.execute((ROOT / "scripts/sovereign-backend/migrations" / migration).read_text())
    with conn.cursor() as cur:
        cur.execute("INSERT INTO admin_users (id) VALUES (%s), (%s)", (OWNER, OTHER))
        cur.execute("""INSERT INTO sovereign_agent_jobs
            (job_id,user_id,executor,repo_url,mission,status,workspace_id,external_ref)
            VALUES (%s,%s,'sovereign-local-runner','https://github.com/test/repository',
                    'Regression test in disposable database','running',%s,%s)""", (JOB, OWNER, JOB, CLAIM))
        cur.execute("""INSERT INTO agent_runs
            (run_id,user_id,job_id,session_key,mission_summary,mission_digest,status,source,
             evidence_id,trace_id,reason,next_action)
            VALUES (%s,%s,%s,%s,'Disposable runtime test',%s,'RUNNING','agents-sdk',
                    'evidence-initial','trace-regression','Runtime regression','WAIT_FOR_FREE_SINGLE_AGENT')""",
                    (RUN, OWNER, JOB, f"session-{JOB}", "a"*64))
    conn.commit()
    try:
        yield conn
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        conn.commit()
        conn.close()


def heartbeat(conn, **kwargs):
    return append_repository_executor_heartbeat(conn, user_id=kwargs.get("user_id", OWNER),
        job_id=JOB, run_id=RUN, claim_ref=kwargs.get("claim_ref", CLAIM))


def clocks(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT updated_at, status FROM sovereign_agent_jobs WHERE job_id=%s", (JOB,))
        job = dict(cur.fetchone())
        cur.execute("SELECT updated_at, status FROM agent_runs WHERE run_id=%s", (RUN,))
        run = dict(cur.fetchone())
    conn.commit()
    return job, run


def test_actual_heartbeat_sql_appends_verifiable_evidence_without_resetting_progress(database):
    before = clocks(database)
    assert heartbeat(database)
    assert heartbeat(database)
    assert clocks(database) == before
    events = read_job_runtime_evidence(database, user_id=OWNER, job_id=JOB, external_ref=CLAIM)
    assert len(events) == 2
    assert all(event["heartbeatCurrent"] is True and event["stage"] == "sovereign_executor_heartbeat" for event in events)
    assert events[0]["eventId"] != events[1]["eventId"]
    assert events[0]["at"] <= events[1]["at"]
    assert read_job_runtime_evidence(database, user_id=OTHER, job_id=JOB, external_ref=CLAIM) == ()


@pytest.mark.parametrize("scope", ["other-owner", "other-claim", "blocked-job"])
def test_actual_sql_rejects_noncurrent_heartbeat_without_writing(database, scope):
    if scope == "blocked-job":
        with database.cursor() as cur:
            cur.execute("UPDATE sovereign_agent_jobs SET status='blocked',blocker='Owner cancellation' WHERE job_id=%s", (JOB,))
        database.commit()
    assert not heartbeat(database, user_id=OTHER if scope == "other-owner" else OWNER,
        claim_ref=CLAIM+"-old" if scope == "other-claim" else CLAIM)
    assert read_job_runtime_evidence(database, user_id=OWNER, job_id=JOB, external_ref=CLAIM) == ()


def test_actual_stage_event_is_visible_and_tampered_payload_fails_validation(database):
    record_agent_stage_event(database, user_id=OWNER, run_id=RUN, trace_id="trace-regression",
        agent_id="free_single_agent", event_type="single_agent_started", status="RUNNING",
        summary="Actual persisted agent stage", next_action="WAIT_FOR_FREE_SINGLE_AGENT",
        evidence_payload={"jobId": JOB, "loop": 1})
    events = read_job_runtime_evidence(database, user_id=OWNER, job_id=JOB, external_ref=CLAIM)
    assert len(events) == 1 and events[0]["summary"] == "Actual persisted agent stage"
    with database.cursor() as cur:
        cur.execute("UPDATE agent_evidence SET payload=%s::jsonb WHERE evidence_id=%s",
                    ('{"jobId":"agent-other"}', events[0]["evidenceId"]))
    database.commit()
    with pytest.raises(ValueError, match="binding or hash"):
        read_job_runtime_evidence(database, user_id=OWNER, job_id=JOB, external_ref=CLAIM)
