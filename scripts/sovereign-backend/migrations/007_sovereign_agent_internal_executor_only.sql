-- Sovereign Agent Runtime: retire all legacy/external executor identities.
BEGIN;
UPDATE sovereign_agent_jobs
SET status = CASE WHEN status IN ('completed','failed','blocked','cleaned') THEN status ELSE 'blocked' END,
    blocker = CASE WHEN status IN ('completed','failed','blocked','cleaned') THEN blocker ELSE COALESCE(blocker, 'Legacy executor retired; resubmit through sovereign-local-runner.') END,
    executor = 'sovereign-local-runner',
    updated_at = NOW()
WHERE executor <> 'sovereign-local-runner';
ALTER TABLE sovereign_agent_jobs DROP CONSTRAINT IF EXISTS sovereign_agent_jobs_executor_check;
ALTER TABLE sovereign_agent_jobs ADD CONSTRAINT sovereign_agent_jobs_executor_check CHECK (executor = 'sovereign-local-runner');
COMMIT;
