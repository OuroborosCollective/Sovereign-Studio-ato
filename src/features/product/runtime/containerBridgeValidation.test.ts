import { describe, expect, it } from 'vitest';
import {
  validateRepoToBuilderBridge,
  validateBuilderToGeneratedFilesBridge,
  validateGeneratedFilesToDiffBridge,
  validateFilesToDraftPRBridge,
  validateWorkflowToFindingsBridge,
  validateRemoteMemoryToPatternMemoryBridge,
  validateTelemetryToCoachBridge,
  validateFullPipeline,
} from './containerBridgeValidation';

describe('containerBridgeValidation', () => {
  describe('validateRepoToBuilderBridge', () => {
    it('passes when all required fields are valid', () => {
      const bridge = {
        repoReady: true,
        fileCount: 5,
        repoUrl: 'https://github.com/owner/repo',
        branch: 'main',
        tokenInLogs: false,
      };
      const result = validateRepoToBuilderBridge(bridge);
      expect(result.valid).toBe(true);
      expect(result.severity).toBe('info');
    });

    it('fails when repo is not ready', () => {
      const bridge = {
        repoReady: false,
        fileCount: 5,
        repoUrl: 'https://github.com/owner/repo',
        branch: 'main',
        tokenInLogs: false,
      };
      const result = validateRepoToBuilderBridge(bridge);
      expect(result.valid).toBe(false);
      expect(result.details).toContain('Repo not ready - snapshot not loaded');
    });

    it('fails when no files in snapshot', () => {
      const bridge = {
        repoReady: true,
        fileCount: 0,
        repoUrl: 'https://github.com/owner/repo',
        branch: 'main',
        tokenInLogs: false,
      };
      const result = validateRepoToBuilderBridge(bridge);
      expect(result.valid).toBe(false);
      expect(result.details).toContain('No files in repository snapshot');
    });

    it('fails with invalid URL', () => {
      const bridge = {
        repoReady: true,
        fileCount: 5,
        repoUrl: 'not-a-valid-url',
        branch: 'main',
        tokenInLogs: false,
      };
      const result = validateRepoToBuilderBridge(bridge);
      expect(result.valid).toBe(false);
      expect(result.details).toContain('Invalid repository URL');
    });

    it('warns when token may be in logs', () => {
      const bridge = {
        repoReady: true,
        fileCount: 5,
        repoUrl: 'https://github.com/owner/repo',
        branch: 'main',
        tokenInLogs: true,
      };
      const result = validateRepoToBuilderBridge(bridge);
      expect(result.severity).toBe('warning');
    });
  });

  describe('validateBuilderToGeneratedFilesBridge', () => {
    it('passes when mission is ready', () => {
      const bridge = {
        mission: 'Add user authentication',
        isPlaceholder: false,
        repoSnapshotReady: true,
        packageHasFiles: true,
        filesActionable: true,
        planOnlyOnly: false,
      };
      const result = validateBuilderToGeneratedFilesBridge(bridge);
      expect(result.valid).toBe(true);
    });

    it('fails when mission is empty', () => {
      const bridge = {
        mission: '   ',
        isPlaceholder: false,
        repoSnapshotReady: true,
        packageHasFiles: true,
        filesActionable: true,
        planOnlyOnly: false,
      };
      const result = validateBuilderToGeneratedFilesBridge(bridge);
      expect(result.valid).toBe(false);
      expect(result.details).toContain('Mission is empty');
    });

    it('warns when mission is placeholder', () => {
      const bridge = {
        mission: 'Example mission placeholder',
        isPlaceholder: true,
        repoSnapshotReady: true,
        packageHasFiles: true,
        filesActionable: true,
        planOnlyOnly: false,
      };
      const result = validateBuilderToGeneratedFilesBridge(bridge);
      expect(result.severity).toBe('warning');
    });

    it('warns when plan-only only mode (but still valid)', () => {
      const bridge = {
        mission: 'Add auth',
        isPlaceholder: false,
        repoSnapshotReady: true,
        packageHasFiles: true,
        filesActionable: true,
        planOnlyOnly: true,
      };
      const result = validateBuilderToGeneratedFilesBridge(bridge);
      // Plan-only is valid but warning
      expect(result.valid).toBe(true);
      expect(result.severity).toBe('warning');
      expect(result.details).toContain('WARNING: Plan-only mode - no actual file generation');
    });
  });

  describe('validateGeneratedFilesToDiffBridge', () => {
    it('passes when package exists and paths valid', () => {
      const bridge = {
        packageExists: true,
        pathsValid: true,
        sourcesLoaded: true,
        isNewFile: false,
      };
      const result = validateGeneratedFilesToDiffBridge(bridge);
      expect(result.valid).toBe(true);
    });

    it('fails when package does not exist', () => {
      const bridge = {
        packageExists: false,
        pathsValid: true,
        sourcesLoaded: true,
        isNewFile: false,
      };
      const result = validateGeneratedFilesToDiffBridge(bridge);
      expect(result.valid).toBe(false);
    });

    it('fails when paths not valid', () => {
      const bridge = {
        packageExists: true,
        pathsValid: false,
        sourcesLoaded: true,
        isNewFile: false,
      };
      const result = validateGeneratedFilesToDiffBridge(bridge);
      expect(result.valid).toBe(false);
    });

    it('handles new file as info, not error', () => {
      const bridge = {
        packageExists: true,
        pathsValid: true,
        sourcesLoaded: true,
        isNewFile: true,
      };
      const result = validateGeneratedFilesToDiffBridge(bridge);
      expect(result.valid).toBe(true);
      expect(result.details).toContain('INFO: New file detected - not an error');
    });
  });

  describe('validateFilesToDraftPRBridge', () => {
    it('passes when all requirements met', () => {
      const bridge = {
        selfReviewAccepted: true,
        actionableOutput: true,
        planOnlyOnly: false,
        tokenPresent: true,
        repoParsed: true,
        branchNonceSafe: true,
        secretsInLogs: false,
      };
      const result = validateFilesToDraftPRBridge(bridge);
      expect(result.valid).toBe(true);
    });

    it('fails when self-review not accepted', () => {
      const bridge = {
        selfReviewAccepted: false,
        actionableOutput: true,
        planOnlyOnly: false,
        tokenPresent: true,
        repoParsed: true,
        branchNonceSafe: true,
        secretsInLogs: false,
      };
      const result = validateFilesToDraftPRBridge(bridge);
      expect(result.valid).toBe(false);
    });

    it('fails when secrets in logs', () => {
      const bridge = {
        selfReviewAccepted: true,
        actionableOutput: true,
        planOnlyOnly: false,
        tokenPresent: true,
        repoParsed: true,
        branchNonceSafe: true,
        secretsInLogs: true,
      };
      const result = validateFilesToDraftPRBridge(bridge);
      expect(result.severity).toBe('error');
      expect(result.details).toContain('ERROR: Secrets detected in logs');
    });
  });

  describe('validateWorkflowToFindingsBridge', () => {
    it('passes with valid workflow result', () => {
      const bridge = {
        commitSha: 'abc123',
        workflowResultValid: true,
        redStatus: false,
        greenStatus: true,
        staleResult: false,
      };
      const result = validateWorkflowToFindingsBridge(bridge);
      expect(result.valid).toBe(true);
    });

    it('fails without commit SHA', () => {
      const bridge = {
        commitSha: null,
        workflowResultValid: true,
        redStatus: false,
        greenStatus: true,
        staleResult: false,
      };
      const result = validateWorkflowToFindingsBridge(bridge);
      expect(result.valid).toBe(false);
    });

    it('warns about stale result', () => {
      const bridge = {
        commitSha: 'abc123',
        workflowResultValid: true,
        redStatus: false,
        greenStatus: false,
        staleResult: true,
      };
      const result = validateWorkflowToFindingsBridge(bridge);
      expect(result.severity).toBe('warning');
    });

    it('indicates repair needed when red', () => {
      const bridge = {
        commitSha: 'abc123',
        workflowResultValid: true,
        redStatus: true,
        greenStatus: false,
        staleResult: false,
      };
      const result = validateWorkflowToFindingsBridge(bridge);
      expect(result.details).toContain('Workflow status RED - repair plan should be generated');
    });
  });

  describe('validateRemoteMemoryToPatternMemoryBridge', () => {
    it('passes when all config valid', () => {
      const bridge = {
        gatewayConfigValid: true,
        contributorId: 'user-123',
        collectionName: 'patterns',
        workspaceId: 'ws-456',
        deleteConfirmationsComplete: true,
        sharedPatternDetected: false,
      };
      const result = validateRemoteMemoryToPatternMemoryBridge(bridge);
      expect(result.valid).toBe(true);
    });

    it('fails when gateway config invalid', () => {
      const bridge = {
        gatewayConfigValid: false,
        contributorId: 'user-123',
        collectionName: 'patterns',
        workspaceId: 'ws-456',
        deleteConfirmationsComplete: true,
        sharedPatternDetected: false,
      };
      const result = validateRemoteMemoryToPatternMemoryBridge(bridge);
      expect(result.valid).toBe(false);
    });

    it('warns when shared pattern detected', () => {
      const bridge = {
        gatewayConfigValid: true,
        contributorId: 'user-123',
        collectionName: 'patterns',
        workspaceId: 'ws-456',
        deleteConfirmationsComplete: true,
        sharedPatternDetected: true,
      };
      const result = validateRemoteMemoryToPatternMemoryBridge(bridge);
      expect(result.severity).toBe('warning');
    });
  });

  describe('validateTelemetryToCoachBridge', () => {
    it('passes when event valid and no secrets', () => {
      const bridge = {
        eventValid: true,
        noSecrets: true,
        stagesKnown: ['init', 'plan', 'build', 'review'],
        latestByStageConsistent: true,
        noisyEventsCount: 3,
      };
      const result = validateTelemetryToCoachBridge(bridge);
      expect(result.valid).toBe(true);
    });

    it('fails when secrets detected', () => {
      const bridge = {
        eventValid: true,
        noSecrets: false,
        stagesKnown: ['init', 'plan'],
        latestByStageConsistent: true,
        noisyEventsCount: 3,
      };
      const result = validateTelemetryToCoachBridge(bridge);
      expect(result.severity).toBe('error');
      expect(result.details).toContain('ERROR: Secrets detected in telemetry');
    });

    it('warns about noisy events', () => {
      const bridge = {
        eventValid: true,
        noSecrets: true,
        stagesKnown: ['init', 'plan'],
        latestByStageConsistent: true,
        noisyEventsCount: 15,
      };
      const result = validateTelemetryToCoachBridge(bridge);
      expect(result.severity).toBe('warning');
    });
  });

  describe('validateFullPipeline', () => {
    it('passes when all bridges valid', () => {
      const bridge = {
        repoToBuilder: {
          repoReady: true,
          fileCount: 5,
          repoUrl: 'https://github.com/owner/repo',
          branch: 'main',
          tokenInLogs: false,
        },
        builderToGeneratedFiles: {
          mission: 'Add auth',
          isPlaceholder: false,
          repoSnapshotReady: true,
          packageHasFiles: true,
          filesActionable: true,
          planOnlyOnly: false,
        },
        generatedFilesToDiff: {
          packageExists: true,
          pathsValid: true,
          sourcesLoaded: true,
          isNewFile: false,
        },
        filesToDraftPR: {
          selfReviewAccepted: true,
          actionableOutput: true,
          planOnlyOnly: false,
          tokenPresent: true,
          repoParsed: true,
          branchNonceSafe: true,
          secretsInLogs: false,
        },
        workflowToFindings: {
          commitSha: 'abc123',
          workflowResultValid: true,
          redStatus: false,
          greenStatus: true,
          staleResult: false,
        },
        remoteMemoryToPatternMemory: {
          gatewayConfigValid: true,
          contributorId: 'user-123',
          collectionName: 'patterns',
          workspaceId: 'ws-456',
          deleteConfirmationsComplete: true,
          sharedPatternDetected: false,
        },
        telemetryToCoach: {
          eventValid: true,
          noSecrets: true,
          stagesKnown: ['init', 'plan'],
          latestByStageConsistent: true,
          noisyEventsCount: 3,
        },
      };
      const result = validateFullPipeline(bridge);
      expect(result.overallValid).toBe(true);
      expect(result.results).toHaveLength(7);
      expect(result.criticalErrors).toHaveLength(0);
    });

    it('reports critical errors', () => {
      const bridge = {
        repoToBuilder: {
          repoReady: false,
          fileCount: 0,
          repoUrl: 'invalid',
          branch: '',
          tokenInLogs: false,
        },
        builderToGeneratedFiles: {
          mission: '',
          isPlaceholder: false,
          repoSnapshotReady: false,
          packageHasFiles: false,
          filesActionable: false,
          planOnlyOnly: false,
        },
        generatedFilesToDiff: {
          packageExists: false,
          pathsValid: false,
          sourcesLoaded: false,
          isNewFile: false,
        },
        filesToDraftPR: {
          selfReviewAccepted: false,
          actionableOutput: false,
          planOnlyOnly: false,
          tokenPresent: false,
          repoParsed: false,
          branchNonceSafe: false,
          secretsInLogs: true,
        },
        workflowToFindings: {
          commitSha: null,
          workflowResultValid: false,
          redStatus: false,
          greenStatus: false,
          staleResult: false,
        },
        remoteMemoryToPatternMemory: {
          gatewayConfigValid: false,
          contributorId: null,
          collectionName: null,
          workspaceId: null,
          deleteConfirmationsComplete: false,
          sharedPatternDetected: false,
        },
        telemetryToCoach: {
          eventValid: false,
          noSecrets: false,
          stagesKnown: [],
          latestByStageConsistent: false,
          noisyEventsCount: 20,
        },
      };
      const result = validateFullPipeline(bridge);
      expect(result.overallValid).toBe(false);
      expect(result.criticalErrors.length).toBeGreaterThan(0);
    });
  });
});