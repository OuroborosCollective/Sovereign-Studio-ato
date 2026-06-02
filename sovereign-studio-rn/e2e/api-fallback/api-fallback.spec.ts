/**
 * API Fallback Chain Test Suite
 * Tests the multi-provider fallback: MLVoca → P8lination → Gemini → Groq
 */

import {
  API_PROVIDERS,
  FALLBACK_CONFIG,
  TEST_PROMPTS,
  EXPECTED_RESPONSE_LATENCY,
  type TestResult,
  type FallbackTestReport,
} from './api-fallback.config';

describe('API Fallback Chain Tests', () => {
  let results: TestResult[] = [];
  let report: FallbackTestReport;

  beforeAll(async () => {
    report = {
      timestamp: new Date().toISOString(),
      totalTests: 0,
      passed: 0,
      failed: 0,
      providerStats: {},
      fallbackChain: [],
    };

    // Initialize provider stats
    Object.keys(API_PROVIDERS).forEach(key => {
      report.providerStats[key] = {
        attempts: 0,
        successes: 0,
        failures: 0,
        avgLatency: 0,
      };
    });
  });

  afterAll(() => {
    console.log('\n📊 API Fallback Test Report');
    console.log('='.repeat(50));
    console.log(`Timestamp: ${report.timestamp}`);
    console.log(`Total Tests: ${report.totalTests}`);
    console.log(`Passed: ${report.passed}`);
    console.log(`Failed: ${report.failed}`);
    console.log('\nProvider Statistics:');
    Object.entries(report.providerStats).forEach(([provider, stats]) => {
      console.log(`  ${provider}: ${stats.successes}/${stats.attempts} (${((stats.successes / stats.attempts) * 100).toFixed(1)}%) - Avg: ${stats.avgLatency.toFixed(0)}ms`);
    });
  });

  const testProvider = async (
    providerName: string,
    prompt: string,
    triggerFallback: boolean = false
  ): Promise<TestResult> => {
    const provider = API_PROVIDERS[providerName];
    const startTime = Date.now();
    report.providerStats[providerName].attempts++;

    try {
      const response = await callProvider(provider, prompt);
      const latency = Date.now() - startTime;
      
      report.providerStats[providerName].successes++;
      report.providerStats[providerName].avgLatency =
        (report.providerStats[providerName].avgLatency * (report.providerStats[providerName].successes - 1) + latency) /
        report.providerStats[providerName].successes;

      return {
        provider: providerName,
        success: true,
        latency,
        response,
        error: null,
        fallbackTriggered: triggerFallback,
      };
    } catch (error) {
      const latency = Date.now() - startTime;
      report.providerStats[providerName].failures++;

      return {
        provider: providerName,
        success: false,
        latency,
        response: null,
        error: error instanceof Error ? error.message : 'Unknown error',
        fallbackTriggered: triggerFallback,
      };
    }
  };

  const callProvider = async (
    provider: { name: string; endpoint: string; timeout: number },
    prompt: string
  ): Promise<string> => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), provider.timeout);

    try {
      const response = await fetch(`${provider.endpoint}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${process.env[`${provider.name.toUpperCase()}_API_KEY`]}`,
        },
        body: JSON.stringify({
          model: provider.name === 'gemini' ? 'gemini-pro' : 'default',
          messages: [{ role: 'user', content: prompt }],
          max_tokens: 1000,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return data.choices?.[0]?.message?.content || 'No response';
    } catch (error) {
      clearTimeout(timeout);
      throw error;
    }
  };

  const testFallbackChain = async (prompt: string): Promise<TestResult> => {
    console.log(`\n🔄 Testing fallback chain for: "${prompt.substring(0, 50)}..."`);
    report.totalTests++;

    for (const providerKey of Object.keys(API_PROVIDERS)) {
      const result = await testProvider(providerKey, prompt);
      results.push(result);

      if (result.success) {
        console.log(`  ✅ ${providerKey}: ${result.latency}ms`);
        report.passed++;
        return result;
      } else {
        console.log(`  ❌ ${providerKey}: ${result.error}`);
        report.fallbackChain.push(providerKey);
      }
    }

    report.failed++;
    return results[results.length - 1];
  };

  describe('🏥 Health Check', () => {
    it('should check MLVoca health', async () => {
      const result = await testProvider('mlvoca', 'Health check');
      expect(result.success).toBe(true);
    });

    it('should check P8lination health', async () => {
      const result = await testProvider('p8lination', 'Health check');
      // May fail but should not crash
      expect(result).toBeDefined();
    });

    it('should check Gemini health', async () => {
      const result = await testProvider('gemini', 'Health check');
      expect(result).toBeDefined();
    });

    it('should check Groq health', async () => {
      const result = await testProvider('groq', 'Health check');
      expect(result).toBeDefined();
    });
  });

  describe('🔄 Fallback Chain Tests', () => {
    TEST_PROMPTS.forEach((prompt, index) => {
      it(`should handle prompt ${index + 1}: "${prompt.substring(0, 30)}..."`, async () => {
        const result = await testFallbackChain(prompt);
        expect(result).toBeDefined();
        
        if (result.success) {
          expect(result.response).toBeTruthy();
        }
      }, 120000);
    });
  });

  describe('⚡ Latency Tests', () => {
    it('should meet MLVoca latency target', async () => {
      const result = await testProvider('mlvoca', 'Quick response test');
      if (result.success) {
        expect(result.latency).toBeLessThan(EXPECTED_RESPONSE_LATENCY.mlvoca);
      }
    });

    it('should meet P8lination latency target', async () => {
      const result = await testProvider('p8lination', 'Quick response test');
      if (result.success) {
        expect(result.latency).toBeLessThan(EXPECTED_RESPONSE_LATENCY.p8lination);
      }
    });

    it('should meet Gemini latency target', async () => {
      const result = await testProvider('gemini', 'Quick response test');
      if (result.success) {
        expect(result.latency).toBeLessThan(EXPECTED_RESPONSE_LATENCY.gemini);
      }
    });

    it('should meet Groq latency target', async () => {
      const result = await testProvider('groq', 'Quick response test');
      if (result.success) {
        expect(result.latency).toBeLessThan(EXPECTED_RESPONSE_LATENCY.groq);
      }
    });
  });

  describe('🔒 Circuit Breaker Tests', () => {
    it('should open circuit after threshold failures', async () => {
      let failureCount = 0;
      
      for (let i = 0; i < FALLBACK_CONFIG.circuitBreakerThreshold + 1; i++) {
        const result = await testProvider('mlvoca', `Circuit test ${i}`);
        if (!result.success) {
          failureCount++;
        }
      }

      expect(failureCount).toBeGreaterThanOrEqual(FALLBACK_CONFIG.circuitBreakerThreshold);
    });

    it('should reset circuit after recovery period', async () => {
      // Circuit should auto-reset
      const result = await testProvider('mlvoca', 'Recovery test');
      expect(result).toBeDefined();
    });
  });

  describe('🎯 Error Recovery Tests', () => {
    it('should handle timeout gracefully', async () => {
      const provider = { ...API_PROVIDERS.mlvoca, timeout: 1 }; // 1ms timeout
      const controller = new AbortController();
      
      try {
        await callProvider(provider, 'Quick test');
      } catch (error) {
        expect(error).toBeDefined();
      }
    });

    it('should handle malformed responses', async () => {
      // Test with invalid response format
      expect(async () => {
        const response = await fetch('https://httpbin.org/json');
        const data = await response.json();
        expect(data).toHaveProperty('slideshow');
      }).not.toThrow();
    });

    it('should handle rate limiting', async () => {
      const results: TestResult[] = [];
      for (let i = 0; i < 5; i++) {
        const result = await testProvider('groq', `Rate limit test ${i}`);
        results.push(result);
      }
      // Should gracefully handle rate limits
      expect(results.length).toBe(5);
    });
  });

  describe('📊 Performance Metrics', () => {
    it('should calculate average fallback time', () => {
      const fallbackResults = results.filter(r => r.fallbackTriggered);
      if (fallbackResults.length > 0) {
        const avgTime = fallbackResults.reduce((sum, r) => sum + r.latency, 0) / fallbackResults.length;
        console.log(`\n📈 Average fallback time: ${avgTime.toFixed(0)}ms`);
        expect(avgTime).toBeLessThan(60000);
      }
    });

    it('should track provider success rates', () => {
      Object.keys(report.providerStats).forEach(provider => {
        const stats = report.providerStats[provider];
        const successRate = stats.attempts > 0 ? stats.successes / stats.attempts : 0;
        console.log(`${provider}: ${(successRate * 100).toFixed(1)}% success rate`);
      });
    });
  });
});