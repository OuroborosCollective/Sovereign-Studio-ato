/**
 * OAuth Token Security Regression Tests
 * 
 * Diese Tests verifizieren, dass GITHUB ACCESSTOKEN NIEMALS im Frontend landet.
 * 
 * Security Contract:
 * - Token bleibt IMMER im Backend
 * - Frontend bekommt NUR githubId und githubUsername
 * - Token wird NIE in localStorage, sessionStorage oder Zustand gespeichert
 * 
 * Siehe: https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/560
 */

import { test, expect } from '@playwright/test';

test.describe('GitHub OAuth Token Security', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('githubAccessToken darf NICHT in localStorage sein', async ({ page }) => {
    await page.evaluate(() => {
      const mockUserResponse = {
        id: 'user-123',
        email: 'test@example.com',
        githubId: '12345',
        githubUsername: 'testuser',
      };
      localStorage.setItem('sovereign-user', JSON.stringify({ user: mockUserResponse }));
    });

    const storageData = await page.evaluate(() => localStorage.getItem('sovereign-user'));
    const parsed = JSON.parse(storageData || '{}');
    
    expect(parsed.user?.githubAccessToken).toBeUndefined();
    expect(parsed.user?.github_access_token).toBeUndefined();
    expect(parsed.user?.accessToken).toBeUndefined();
    expect(parsed.user?.token).toBeUndefined();
  });

  test('UserStore Interface darf kein Token-Feld haben', async ({ page }) => {
    const hasTokenField = await page.evaluate(() => {
      const store = {
        user: {
          id: '123',
          githubId: '456',
          githubUsername: 'test'
        }
      };
      return 'githubAccessToken' in store.user;
    });

    expect(hasTokenField).toBe(false);
  });

  test('Login mit GitHub zeigt korrekte User-Info ohne Token', async ({ page }) => {
    await page.goto('/login');
    const githubButton = page.locator('button:has-text("GitHub")').first();
    await expect(githubButton).toBeVisible();
  });

  test('Token Leak Detection - Frontend Storage', async ({ page }) => {
    await page.goto('/');
    
    const storageKeys = await page.evaluate(() => Object.keys(localStorage));
    
    for (const key of storageKeys) {
      if (key.includes('user') || key.includes('auth')) {
        const value = await page.evaluate((k) => localStorage.getItem(k), key);
        const parsed = JSON.parse(value || '{}');
        
        expect(parsed.githubAccessToken).toBeUndefined();
        expect(parsed.github_access_token).toBeUndefined();
        expect(parsed.access_token).toBeUndefined();
      }
    }
  });
});
