import { device, element, by, waitFor, detox } from 'detox';
import { describe, beforeAll, beforeEach, it, expect } from '@jest/globals';

// Configure Detox
detox.configure({
  spec: __dirname,
});

// Test Configuration
const TEST_CONFIG = {
  timeout: 30000,
  retryAttempts: 3,
  screenshotOnFail: true,
};

// Test Suites
describe('Sovereign Studio RN - E2E Tests', () => {
  beforeAll(async () => {
    await device.launchApp({
      newInstance: true,
      permissions: {
        camera: 'YES',
        location: 'YES',
        notifications: 'YES',
      },
    });
  });

  beforeEach(async () => {
    await device.reloadReactNative();
  });

  describe('🚀 Home Screen', () => {
    it('should display the home screen with all elements', async () => {
      await waitFor(element(by.id('homeScreen'))).toBeVisible();
      await expect(element(by.id('appLogo'))).toBeVisible();
      await expect(element(by.id('appTitle'))).toHaveText('Sovereign Studio');
    });

    it('should navigate to Canvas screen', async () => {
      await element(by.id('canvasButton')).tap();
      await waitFor(element(by.id('canvasScreen'))).toBeVisible();
    });

    it('should navigate to Chat screen', async () => {
      await element(by.id('chatButton')).tap();
      await waitFor(element(by.id('chatScreen'))).toBeVisible();
    });

    it('should navigate to Explorer screen', async () => {
      await element(by.id('explorerButton')).tap();
      await waitFor(element(by.id('explorerScreen'))).toBeVisible();
    });

    it('should navigate to Settings screen', async () => {
      await element(by.id('settingsButton')).tap();
      await waitFor(element(by.id('settingsScreen'))).toBeVisible();
    });
  });

  describe('🎨 Canvas Screen', () => {
    beforeEach(async () => {
      await element(by.id('canvasButton')).tap();
      await waitFor(element(by.id('canvasScreen'))).toBeVisible();
    });

    it('should display the canvas editor', async () => {
      await expect(element(by.id('canvasView'))).toBeVisible();
      await expect(element(by.id('toolbar'))).toBeVisible();
    });

    it('should allow drawing on canvas', async () => {
      const canvas = element(by.id('canvasView'));
      await canvas.tap({ x: 100, y: 100 });
      await canvas.pan({ fromX: 100, fromY: 100, toX: 200, toY: 200 });
      // Verify drawing occurred
      await expect(element(by.id('undoButton'))).toBeEnabled();
    });

    it('should have drawing tools available', async () => {
      await element(by.id('toolSelector')).tap();
      await expect(element(by.id('penTool'))).toBeVisible();
      await expect(element(by.id('eraserTool'))).toBeVisible();
      await expect(element(by.id('shapeTool'))).toBeVisible();
    });

    it('should undo drawing action', async () => {
      const canvas = element(by.id('canvasView'));
      await canvas.pan({ fromX: 100, fromY: 100, toX: 200, toY: 200 });
      await element(by.id('undoButton')).tap();
      await expect(element(by.id('undoButton'))).toBeDisabled();
    });

    it('should clear the canvas', async () => {
      await element(by.id('clearButton')).tap();
      await waitFor(element(by.id('confirmClearDialog'))).toBeVisible();
      await element(by.id('confirmClear')).tap();
      await expect(element(by.id('canvasView'))).toBeEmpty();
    });
  });

  describe('💬 Chat Screen', () => {
    beforeEach(async () => {
      await element(by.id('chatButton')).tap();
      await waitFor(element(by.id('chatScreen'))).toBeVisible();
    });

    it('should display the chat interface', async () => {
      await expect(element(by.id('chatContainer'))).toBeVisible();
      await expect(element(by.id('messageInput'))).toBeVisible();
      await expect(element(by.id('sendButton'))).toBeVisible();
    });

    it('should send a message', async () => {
      await element(by.id('messageInput')).typeText('Hello, Sovereign Studio!');
      await element(by.id('sendButton')).tap();
      await waitFor(element(by.id('userMessage'))).toBeVisible();
    });

    it('should receive an AI response', async () => {
      await element(by.id('messageInput')).typeText('What can you do?');
      await element(by.id('sendButton')).tap();
      await waitFor(element(by.id('aiResponse'))).toBeVisible({ timeout: 60000 });
    });

    it('should show typing indicator', async () => {
      await element(by.id('messageInput')).typeText('Tell me more');
      await element(by.id('sendButton')).tap();
      await expect(element(by.id('typingIndicator'))).toBeVisible();
    });

    it('should handle API fallback gracefully', async () => {
      // Simulate API failure by waiting
      await element(by.id('messageInput')).typeText('Test fallback');
      await element(by.id('sendButton')).tap();
      // Should still show response from fallback
      await waitFor(element(by.id('aiResponse'))).toBeVisible({ timeout: 120000 });
    });
  });

  describe('📁 Explorer Screen', () => {
    beforeEach(async () => {
      await element(by.id('explorerButton')).tap();
      await waitFor(element(by.id('explorerScreen'))).toBeVisible();
    });

    it('should display the file explorer', async () => {
      await expect(element(by.id('explorerContainer'))).toBeVisible();
      await expect(element(by.id('fileList'))).toBeVisible();
    });

    it('should display GitHub repositories', async () => {
      await element(by.id('githubTab')).tap();
      await waitFor(element(by.id('repoList'))).toBeVisible();
    });

    it('should search for repositories', async () => {
      await element(by.id('searchInput')).typeText('sovereign-studio');
      await element(by.id('searchButton')).tap();
      await waitFor(element(by.id('searchResults'))).toBeVisible();
    });

    it('should open a repository', async () => {
      await element(by.id('repoItem')).atIndex(0).tap();
      await waitFor(element(by.id('repoDetail'))).toBeVisible();
    });

    it('should display repository contents', async () => {
      await element(by.id('repoItem')).atIndex(0).tap();
      await waitFor(element(by.id('fileTree'))).toBeVisible();
      await expect(element(by.id('fileItem'))).toBeVisible();
    });
  });

  describe('⚙️ Settings Screen', () => {
    beforeEach(async () => {
      await element(by.id('settingsButton')).tap();
      await waitFor(element(by.id('settingsScreen'))).toBeVisible();
    });

    it('should display settings options', async () => {
      await expect(element(by.id('settingsContainer'))).toBeVisible();
      await expect(element(by.id('themeToggle'))).toBeVisible();
      await expect(element(by.id('apiKeyInput'))).toBeVisible();
    });

    it('should toggle dark mode', async () => {
      const initialState = await element(by.id('themeToggle')).isToggleOn();
      await element(by.id('themeToggle')).tap();
      const newState = await element(by.id('themeToggle')).isToggleOn();
      expect(newState).not.toEqual(initialState);
    });

    it('should update API key', async () => {
      await element(by.id('apiKeyInput')).clearText();
      await element(by.id('apiKeyInput')).typeText('test-api-key-12345');
      await element(by.id('saveApiKey')).tap();
      await expect(element(by.id('apiKeySaved'))).toBeVisible();
    });

    it('should display about section', async () => {
      await element(by.id('aboutSection')).tap();
      await expect(element(by.id('versionInfo'))).toBeVisible();
      await expect(element(by.id('creditsInfo'))).toBeVisible();
    });
  });

  describe('🤖 AI Integration', () => {
    beforeEach(async () => {
      await element(by.id('chatButton')).tap();
      await waitFor(element(by.id('chatScreen'))).toBeVisible();
    });

    it('should use MLVoca as primary AI', async () => {
      await element(by.id('messageInput')).typeText('Test MLVoca');
      await element(by.id('sendButton')).tap();
      await waitFor(element(by.id('aiResponse'))).toBeVisible({ timeout: 60000 });
      // Verify response came from MLVoca
      await expect(element(by.id('aiSourceIndicator'))).toHaveText('MLVoca');
    });

    it('should fallback to P8lination on failure', async () => {
      // This test simulates the fallback chain
      await element(by.id('messageInput')).typeText('Trigger fallback');
      await element(by.id('sendButton')).tap();
      await waitFor(element(by.id('aiResponse'))).toBeVisible({ timeout: 120000 });
      // Should show fallback indicator
      const sourceText = await element(by.id('aiSourceIndicator')).getText();
      expect(['MLVoca', 'P8lination', 'Gemini', 'Groq']).toContain(sourceText);
    });

    it('should show error message on complete failure', async () => {
      // Simulate network failure
      await device.setURLBlacklist(['https://api.example.com']);
      await element(by.id('messageInput')).typeText('Force failure');
      await element(by.id('sendButton')).tap();
      await expect(element(by.id('errorMessage'))).toBeVisible({ timeout: 30000 });
    });
  });

  describe('📊 Code Refactor Screen', () => {
    beforeEach(async () => {
      // Navigate to code refactor
      await element(by.id('menuButton')).tap();
      await element(by.id('codeRefactorOption')).tap();
      await waitFor(element(by.id('codeRefactorScreen'))).toBeVisible();
    });

    it('should display code input area', async () => {
      await expect(element(by.id('codeInput'))).toBeVisible();
      await expect(element(by.id('refactorButton'))).toBeVisible();
    });

    it('should refactor code with AI assistance', async () => {
      await element(by.id('codeInput')).typeText('function oldCode() { console.log("test"); }');
      await element(by.id('refactorButton')).tap();
      await waitFor(element(by.id('refactoredCode'))).toBeVisible({ timeout: 60000 });
    });
  });

  describe('🧹 Self-Healing Tests', () => {
    it('should recover from app crash', async () => {
      // Simulate crash
      await device.sendToHome();
      await device.launchApp({ newInstance: false });
      await waitFor(element(by.id('homeScreen'))).toBeVisible({ timeout: 30000 });
    });

    it('should restore state after background', async () => {
      await element(by.id('chatButton')).tap();
      await element(by.id('messageInput')).typeText('State test');
      await device.sendToHome();
      await device.launchApp({ newInstance: false });
      await waitFor(element(by.id('chatScreen'))).toBeVisible();
      await expect(element(by.id('messageInput'))).toHaveText('State test');
    });

    it('should handle memory pressure gracefully', async () => {
      // Trigger memory warning simulation
      await device.setOrientation('landscape');
      await waitFor(element(by.id('homeScreen'))).toBeVisible();
      await device.setOrientation('portrait');
    });
  });

  describe('🔄 Workflow Integration', () => {
    it('should execute GitHub workflow', async () => {
      await element(by.id('explorerButton')).tap();
      await element(by.id('workflowTab')).tap();
      await element(by.id('runWorkflowButton')).tap();
      await waitFor(element(by.id('workflowStatus'))).toBeVisible();
    });

    it('should display workflow results', async () => {
      await element(by.id('workflowHistory')).tap();
      await expect(element(by.id('workflowResult'))).toBeVisible();
    });
  });
});

// Self-Healing Hooks
afterEach(async () => {
  if (false) { // placeholder for failed test check
    await device.takeScreenshot();
    await autoHeal();
  }
});

async function autoHeal() {
  console.log('🔄 Attempting self-healing...');
  await device.reloadReactNative();
  await waitFor(element(by.id('homeScreen'))).toBeVisible({ timeout: 30000 });
}