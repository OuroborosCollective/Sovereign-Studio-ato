import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RepoInsightPanelBridge } from './RepoInsightPanelBridge';
import type { RepoFile } from '../../github/types';
import type { ScanFindingRegistry } from '../runtime/scanFindingRegistry';
import type { SolutionPatternStore } from '../runtime/solutionPatternMemory';

describe('RepoInsightPanelBridge optimized gating logic', () => {
  const mockRepoFiles: RepoFile[] = [
    { path: 'src/features/product/components/RepoInsightPanel.tsx', type: 'file', size: 100, sha: '123' },
    { path: 'src/features/product/components/RepoInsightPanelBridge.tsx', type: 'file', size: 100, sha: '124' },
    { path: 'README.md', type: 'file', size: 100, sha: '125' },
  ];

  const mockScanRegistry: ScanFindingRegistry = {
    findings: [],
    updatedAt: Date.now(),
  };

  const mockSolutionPatternStore: SolutionPatternStore = {
    version: 1,
    patterns: [],
    rejections: [],
    updatedAt: Date.now(),
  };

  it('correctly gates features as allowed when repo files match evidence', () => {
    const onSuggestionClick = vi.fn();

    render(
      <RepoInsightPanelBridge
        repoFiles={mockRepoFiles}
        scanRegistry={mockScanRegistry}
        workflowReport={null}
        solutionPatternStore={mockSolutionPatternStore}
        currentMission=""
        onSuggestionClick={onSuggestionClick}
      />
    );

    // 'Mehr Komponenten-Tests' is allowed because components exist in repoFiles.
    const allowedBtn = screen.getByRole('button', { name: /Mehr Komponenten-Tests/i });
    expect(allowedBtn).toBeDefined();
    expect(allowedBtn.getAttribute('disabled')).toBeNull();
    expect(allowedBtn.getAttribute('data-gate-state')).toBe('allowed');

    fireEvent.click(allowedBtn);
    expect(onSuggestionClick).toHaveBeenCalled();
  });

  it('gates and blocks feature suggestions when a critical blocker is present', () => {
    const onSuggestionClick = vi.fn();

    // Add a critical scan finding to act as a blocker
    const blockedScanRegistry: ScanFindingRegistry = {
      findings: [
        {
          id: 'find-1',
          title: 'Kritisches Sicherheitsrisiko',
          description: 'Ein kritisches Leck wurde gefunden.',
          filePath: 'src/features/product/components/RepoInsightPanel.tsx',
          category: 'security-leak',
          severity: 'critical',
          status: 'active',
          createdAt: Date.now(),
        }
      ],
      updatedAt: Date.now(),
    };

    render(
      <RepoInsightPanelBridge
        repoFiles={mockRepoFiles}
        scanRegistry={blockedScanRegistry}
        workflowReport={null}
        solutionPatternStore={mockSolutionPatternStore}
        currentMission=""
        onSuggestionClick={onSuggestionClick}
      />
    );

    // Feature suggestions should now be blocked due to the critical blocker
    const blockedBtn = screen.getByRole('button', { name: /Mehr Komponenten-Tests/i });
    expect(blockedBtn).toBeDefined();
    expect(blockedBtn.getAttribute('disabled')).not.toBeNull();
    expect(blockedBtn.getAttribute('data-gate-state')).toBe('blocked');

    fireEvent.click(blockedBtn);
    expect(onSuggestionClick).not.toHaveBeenCalled();
  });
});
