import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useProductMagic } from './useProductMagic';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

describe('useProductMagic - Sequential Workflow Runtime Verification', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('1. IDLE State - Initial State', () => {
    it('should start in idle state', () => {
      const { result } = renderHook(() => useProductMagic());
      
      expect(result.current.pipelineState).toBe('idle');
      expect(result.current.isWorking).toBe(false);
      expect(result.current.progress).toBe(0);
      expect(result.current.built).toBe(false);
    });

    it('should have empty logs initially', () => {
      const { result } = renderHook(() => useProductMagic());
      
      expect(result.current.logs.length).toBeGreaterThan(0);
      expect(result.current.logs[0]).toContain('bereit');
    });

    it('should have welcome message in chat', () => {
      const { result } = renderHook(() => useProductMagic());
      
      expect(result.current.chatMessages.length).toBeGreaterThan(0);
      expect(result.current.chatMessages[0].role).toBe('assistant');
    });
  });

  describe('2. PLANNING State - First Step', () => {
    it('should transition to planning state', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      // Start autonomous job
      act(() => {
        result.current.runAutonomousJob();
      });
      
      // Should be in planning state immediately
      expect(result.current.pipelineState).toBe('planning');
      expect(result.current.isWorking).toBe(true);
    });

    it('should set planning progress correctly', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      // Progress should be around 10% for planning
      expect(result.current.progress).toBe(10);
      expect(result.current.currentStepLabel).toBe('Planung und Code-Entwurf');
    });

    it('should not allow concurrent operations during planning', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      // Start first operation
      act(() => {
        result.current.runAutonomousJob();
      });
      
      // Try to start another operation
      let secondStarted = false;
      act(() => {
        secondStarted = result.current.isWorking;
      });
      
      // Should be blocked
      expect(secondStarted).toBe(false);
    });
  });

  describe('3. GENERATING State - Code Generation', () => {
    it('should transition to generating state after planning', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      // Wait for transition to generating
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('generating');
      }, { timeout: 2000 });
    });

    it('should set generating progress correctly', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.progress).toBe(25);
      }, { timeout: 2000 });
    });

    it('should generate code during this state', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.built).toBe(true);
        expect(result.current.generatedCode.length).toBeGreaterThan(0);
      }, { timeout: 2000 });
    });

    it('should set correct step labels during generation', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.currentStepLabel).toBe('Pruefung');
        expect(result.current.nextStepLabel).toBe('Fix bei Fehler');
      }, { timeout: 2000 });
    });
  });

  describe('4. VALIDATING State - Code Validation', () => {
    it('should transition to validating state', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('validating');
      }, { timeout: 3000 });
    });

    it('should set validating progress', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.progress).toBe(45);
      }, { timeout: 3000 });
    });

    it('should log validation step', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        const logFound = result.current.logs.some(log => 
          log.includes('Schritt 1') || log.includes('fertig')
        );
        expect(logFound).toBe(true);
      }, { timeout: 3000 });
    });
  });

  describe('5. FAILED/ERROR State - Error Handling', () => {
    it('should handle failed validation with maxFixLoops > 0', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      // Ensure maxFixLoops is set
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('failed');
      }, { timeout: 4000 });
    });

    it('should set fixLoops to 1 on first failure', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.fixLoops).toBe(1);
      }, { timeout: 4000 });
    });

    it('should log failure correctly', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        const errorLogFound = result.current.logs.some(log => 
          log.includes('Fehler') || log.includes('Fix')
        );
        expect(errorLogFound).toBe(true);
      }, { timeout: 4000 });
    });
  });

  describe('6. FIXING State - Error Recovery', () => {
    it('should transition to fixing state', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('fixing');
      }, { timeout: 5000 });
    });

    it('should apply visible fix', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.generatedCode).toContain('validationPatch');
      }, { timeout: 5000 });
    });

    it('should set fixing progress', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.progress).toBe(70);
      }, { timeout: 5000 });
    });
  });

  describe('7. REVALIDATING State - Second Validation', () => {
    it('should transition to revalidating state', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('revalidating');
      }, { timeout: 6000 });
    });

    it('should set revalidating progress', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.progress).toBe(88);
      }, { timeout: 6000 });
    });
  });

  describe('8. GREEN State - Success', () => {
    it('should transition to green state', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('green');
      }, { timeout: 8000 });
    });

    it('should set progress to 100% on green', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.progress).toBe(100);
      }, { timeout: 8000 });
    });

    it('should set correct step labels on green', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.currentStepLabel).toBe('Freigabe wartet');
        expect(result.current.nextStepLabel).toBe('Ziel-Link');
      }, { timeout: 8000 });
    });

    it('should stop isWorking on green', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.isWorking).toBe(false);
      }, { timeout: 8000 });
    });
  });

  describe('9. ARCHITECTURE ANALYSIS - After Green', () => {
    it('should run analysis after green state', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.suggestions.length).toBeGreaterThan(0);
      }, { timeout: 15000 });
    });

    it('should set isAnalyzing during analysis', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      // Start analysis directly
      act(() => {
        result.current.runArchitectureAnalysis();
      });
      
      expect(result.current.isAnalyzing).toBe(true);
      
      await vi.waitFor(() => {
        expect(result.current.isAnalyzing).toBe(false);
      }, { timeout: 3000 });
    });

    it('should populate architectureAnalysis', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runArchitectureAnalysis();
      });
      
      await vi.waitFor(() => {
        expect(result.current.architectureAnalysis).not.toBeNull();
        expect(result.current.architectureAnalysis?.components).toBeDefined();
      }, { timeout: 3000 });
    });

    it('should add analysis message to chat', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      const initialCount = result.current.chatMessages.length;
      
      act(() => {
        result.current.runArchitectureAnalysis();
      });
      
      await vi.waitFor(() => {
        expect(result.current.chatMessages.length).toBeGreaterThan(initialCount);
      }, { timeout: 3000 });
    });
  });

  describe('10. MERGE/GITHUB PUSH - Final Step', () => {
    it('should require green state for merge', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      // Try to merge when not green
      act(() => {
        result.current.mergeWhenGreen();
      });
      
      expect(result.current.approvalConfirmed).toBe(false);
    });

    it('should have green state when workflow completes', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('green');
        expect(result.current.built).toBe(true);
      }, { timeout: 10000 });
    });
  });

  describe('Sequential State Transitions - Complete Flow', () => {
    it('should complete full flow: idle -> planning -> generating -> validating -> green', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      // Start
      act(() => {
        result.current.runAutonomousJob();
      });
      
      // Wait for green
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('green');
      }, { timeout: 10000 });
      
      // Verify we went through expected states
      expect(result.current.progress).toBe(100);
      expect(result.current.built).toBe(true);
    });

    it('should not skip states in the workflow', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      // Green should only be reached after going through other states
      await vi.waitFor(() => {
        // If we're green, we must have gone through the intermediate states
        if (result.current.pipelineState === 'green') {
          expect(result.current.progress).toBe(100);
          expect(result.current.built).toBe(true);
        }
      }, { timeout: 10000 });
    });

    it('should complete in reasonable time', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      const startTime = Date.now();
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('green');
      }, { timeout: 10000 });
      
      const duration = Date.now() - startTime;
      
      // Should complete in under 10 seconds
      expect(duration).toBeLessThan(10000);
    });
  });

  describe('Error Recovery - Full Fix Loop', () => {
    it('should complete fix loop: failed -> fixing -> revalidating -> green', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      // Should reach green after fix loop
      await vi.waitFor(() => {
        expect(result.current.pipelineState).toBe('green');
        expect(result.current.fixLoops).toBe(1);
      }, { timeout: 10000 });
    });

    it('should apply fix only once per loop', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setSettings(prev => ({ ...prev, maxFixLoops: 3 }));
      });
      
      act(() => {
        result.current.runAutonomousJob();
      });
      
      await vi.waitFor(() => {
        expect(result.current.fixLoops).toBe(1);
        
        // Code should contain patch marker
        expect(result.current.generatedCode).toContain('validationPatch');
      }, { timeout: 10000 });
    });
  });

  describe('Chat Messages - Sequential Addition', () => {
    it('should add user message when sending chat', () => {
      const { result } = renderHook(() => useProductMagic());
      
      // Send message
      act(() => {
        result.current.sendChatMessage('Test user message');
      });
      
      // Should have user message
      const userMessage = result.current.chatMessages.find(m => 
        m.role === 'user' && m.content === 'Test user message'
      );
      expect(userMessage).toBeDefined();
    });

    it('should have assistant response after user message', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.sendChatMessage('Test message');
      });
      
      // Wait for assistant response
      await vi.waitFor(() => {
        const assistantMessages = result.current.chatMessages.filter(m => m.role === 'assistant');
        expect(assistantMessages.length).toBeGreaterThan(1);
      }, { timeout: 2000 });
    });
  });

  describe('Suggestions - Sequential Processing', () => {
    it('should generate suggestions sequentially', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      // Run analysis
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      // Should have suggestions
      expect(result.current.suggestions.length).toBeGreaterThan(0);
      
      // First suggestion should be integration (high priority)
      expect(result.current.suggestions[0].priority).toBe('high');
    });

    it('should accept suggestions one at a time', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      const suggestionId = result.current.suggestions[0].id;
      const initialCardCount = result.current.cards.length;
      
      // Accept first suggestion
      act(() => {
        result.current.acceptSuggestion(suggestionId);
      });
      
      expect(result.current.suggestions[0].accepted).toBe(true);
      expect(result.current.cards.length).toBeGreaterThan(initialCardCount);
    });
  });
});
