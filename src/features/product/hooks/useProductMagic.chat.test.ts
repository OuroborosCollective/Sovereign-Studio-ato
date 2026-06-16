import { describe, it, expect, vi, beforeEach } from 'vitest';
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

describe('useProductMagic - Chat Features', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
  });

  describe('Initial State', () => {
    it('should have welcome message in chatMessages', () => {
      const { result } = renderHook(() => useProductMagic());
      
      expect(result.current.chatMessages).toBeDefined();
      expect(result.current.chatMessages.length).toBeGreaterThan(0);
      expect(result.current.chatMessages[0].role).toBe('assistant');
      expect(result.current.chatMessages[0].content).toContain('Willkommen');
    });

    it('should have empty suggestions initially', () => {
      const { result } = renderHook(() => useProductMagic());
      
      expect(result.current.suggestions).toEqual([]);
    });

    it('should have null architectureAnalysis initially', () => {
      const { result } = renderHook(() => useProductMagic());
      
      expect(result.current.architectureAnalysis).toBeNull();
    });

    it('should have isAnalyzing false initially', () => {
      const { result } = renderHook(() => useProductMagic());
      
      expect(result.current.isAnalyzing).toBe(false);
    });
  });

  describe('sendChatMessage', () => {
    it('should add user message when sending chat', () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.sendChatMessage('Test message');
      });
      
      const userMessage = result.current.chatMessages.find(
        m => m.role === 'user' && m.content === 'Test message'
      );
      expect(userMessage).toBeDefined();
    });

    it('should add assistant response after user message', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.sendChatMessage('Test message');
      });
      
      await waitFor(() => {
        const assistantMessages = result.current.chatMessages.filter(m => m.role === 'assistant');
        expect(assistantMessages.length).toBeGreaterThan(1); // Initial + response
      });
    });

    it('should respond to "was kannst" with capabilities', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.sendChatMessage('Was kannst du machen?');
      });
      
      await waitFor(() => {
        const responses = result.current.chatMessages.filter(
          m => m.role === 'assistant' && m.content.includes('analysieren')
        );
        expect(responses.length).toBeGreaterThan(0);
      });
    });

    it('should respond to "hilfe" with instructions', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.sendChatMessage('Hilfe bitte');
      });
      
      await waitFor(() => {
        const responses = result.current.chatMessages.filter(
          m => m.role === 'assistant' && m.content.includes('Sovereign Studio')
        );
        expect(responses.length).toBeGreaterThan(0);
      });
    });

    it('should not add empty messages', () => {
      const { result } = renderHook(() => useProductMagic());
      const initialCount = result.current.chatMessages.length;
      
      act(() => {
        result.current.sendChatMessage('');
      });
      
      expect(result.current.chatMessages.length).toBe(initialCount);
    });

    it('should not add whitespace-only messages', () => {
      const { result } = renderHook(() => useProductMagic());
      const initialCount = result.current.chatMessages.length;
      
      act(() => {
        result.current.sendChatMessage('   ');
      });
      
      expect(result.current.chatMessages.length).toBe(initialCount);
    });
  });

  describe('runArchitectureAnalysis', () => {
    it('should set isAnalyzing to true during analysis', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.runArchitectureAnalysis();
      });
      
      expect(result.current.isAnalyzing).toBe(true);
    });

    it('should generate suggestions after analysis', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      expect(result.current.suggestions.length).toBeGreaterThan(0);
    });

    it('should set architectureAnalysis after completion', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      expect(result.current.architectureAnalysis).toBeDefined();
      expect(result.current.architectureAnalysis?.summary).toBeDefined();
    });

    it('should detect API components from blueprint', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setBlueprint('Build an API server with REST endpoints');
      });
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      expect(result.current.architectureAnalysis?.components).toContain('Backend API Server');
    });

    it('should detect Auth components from blueprint', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setBlueprint('Login and registration system with JWT auth');
      });
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      expect(result.current.architectureAnalysis?.components).toContain('Authentication System');
    });

    it('should suggest integrations based on detected components', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setBlueprint('Chat application with real-time messaging');
      });
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      const hasIntegration = result.current.suggestions.some(
        s => s.type === 'feature' && s.title.includes('Integration')
      );
      expect(hasIntegration).toBe(true);
    });

    it('should flag missing auth as security issue', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      act(() => {
        result.current.setBlueprint('User management dashboard with profiles');
      });
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      const hasSecurityIssue = result.current.suggestions.some(
        s => s.type === 'error' && s.title.includes('Security')
      );
      expect(hasSecurityIssue).toBe(true);
    });

    it('should add analysis messages to chat', async () => {
      const { result } = renderHook(() => useProductMagic());
      const initialCount = result.current.chatMessages.length;
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      expect(result.current.chatMessages.length).toBeGreaterThan(initialCount);
    });
  });

  describe('acceptSuggestion', () => {
    it('should mark suggestion as accepted', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      // First run analysis to generate suggestions
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      const suggestionId = result.current.suggestions[0]?.id;
      if (suggestionId) {
        act(() => {
          result.current.acceptSuggestion(suggestionId);
        });
        
        const acceptedSuggestion = result.current.suggestions.find(s => s.id === suggestionId);
        expect(acceptedSuggestion?.accepted).toBe(true);
      }
    });

    it('should add suggestion as a new card/task', async () => {
      const { result } = renderHook(() => useProductMagic());
      const initialCardCount = result.current.cards.length;
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      const suggestionId = result.current.suggestions[0]?.id;
      if (suggestionId) {
        act(() => {
          result.current.acceptSuggestion(suggestionId);
        });
        
        expect(result.current.cards.length).toBeGreaterThan(initialCardCount);
      }
    });

    it('should switch to editor view when accepting suggestion', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      const suggestionId = result.current.suggestions[0]?.id;
      if (suggestionId) {
        act(() => {
          result.current.acceptSuggestion(suggestionId);
        });
        
        expect(result.current.workView).toBe('editor');
      }
    });

    it('should switch mobilePane to live when accepting suggestion', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      const suggestionId = result.current.suggestions[0]?.id;
      if (suggestionId) {
        act(() => {
          result.current.acceptSuggestion(suggestionId);
        });
        
        expect(result.current.mobilePane).toBe('live');
      }
    });

    it('should add assistant message confirming acceptance', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      await act(async () => {
        await result.current.runArchitectureAnalysis();
      });
      
      const suggestionId = result.current.suggestions[0]?.id;
      const suggestionTitle = result.current.suggestions[0]?.title;
      
      if (suggestionId && suggestionTitle) {
        const initialAssistantCount = result.current.chatMessages.filter(
          m => m.role === 'assistant'
        ).length;
        
        act(() => {
          result.current.acceptSuggestion(suggestionId);
        });
        
        const newAssistantCount = result.current.chatMessages.filter(
          m => m.role === 'assistant'
        ).length;
        
        expect(newAssistantCount).toBeGreaterThan(initialAssistantCount);
      }
    });
  });

  describe('targetLink State', () => {
    it('should have empty targetLink initially', () => {
      const { result } = renderHook(() => useProductMagic());
      
      expect(result.current.targetLink).toBe('');
    });

    it('should export targetLink in return object', () => {
      const { result } = renderHook(() => useProductMagic());
      
      expect(result.current.targetLink).toBeDefined();
    });
  });

  describe('Integration: runAutonomousJob triggers analysis', () => {
    it('should run architecture analysis after autonomous job completes', async () => {
      const { result } = renderHook(() => useProductMagic());
      
      // Set blueprint to ensure analysis has content
      act(() => {
        result.current.setBlueprint('Build a chat app with notifications');
      });
      
      // Run autonomous job (mock the async behavior)
      act(() => {
        result.current.runAutonomousJob();
      });
      
      // Wait for the job to complete (includes analysis)
      await waitFor(() => {
        expect(result.current.suggestions.length).toBeGreaterThan(0);
      }, { timeout: 5000 });
    });
  });
});
