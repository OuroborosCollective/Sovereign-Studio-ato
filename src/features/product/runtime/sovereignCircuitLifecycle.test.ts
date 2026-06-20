import { describe, expect, it, vi, beforeEach } from 'vitest';

interface CircuitBreakerState {
  failures: number;
  lastFailure: number;
  state: 'closed' | 'open' | 'half-open';
}

function createCircuitBreaker(threshold = 5, timeout = 30000) {
  const breaker: CircuitBreakerState = {
    failures: 0,
    lastFailure: 0,
    state: 'closed',
  };

  return {
    async call<T>(fn: () => Promise<T>): Promise<T> {
      if (breaker.state === 'open') {
        if (Date.now() - breaker.lastFailure > timeout) {
          breaker.state = 'half-open';
        } else {
          throw new Error(`Circuit breaker open`);
        }
      }
      try {
        const result = await fn();
        breaker.failures = 0;
        breaker.state = 'closed';
        return result;
      } catch (error) {
        breaker.failures++;
        breaker.lastFailure = Date.now();
        if (breaker.failures >= threshold) {
          breaker.state = 'open';
        }
        throw error;
      }
    },
    getState: () => ({ ...breaker }),
  };
}

describe('sovereignCircuitLifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it('starts in closed state', () => {
    const breaker = createCircuitBreaker();
    expect(breaker.getState().state).toBe('closed');
  });

  it('allows successful calls to pass through', async () => {
    const breaker = createCircuitBreaker();
    const result = await breaker.call(() => Promise.resolve('success'));
    expect(result).toBe('success');
    expect(breaker.getState().state).toBe('closed');
  });

  it('opens after threshold failures', async () => {
    const breaker = createCircuitBreaker(3);

    for (let i = 0; i < 3; i++) {
      await expect(
        breaker.call(() => Promise.reject(new Error('failure')))
      ).rejects.toThrow('failure');
    }

    await expect(
      breaker.call(() => Promise.resolve('should not reach'))
    ).rejects.toThrow('Circuit breaker open');
  });

  it('transitions to half-open after timeout', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2024, 0, 1, 12, 0, 0));

    const breaker = createCircuitBreaker(2, 1000);

    // Trigger failures to open the circuit
    await expect(
      breaker.call(() => Promise.reject(new Error('f1')))
    ).rejects.toThrow('f1');
    await expect(
      breaker.call(() => Promise.reject(new Error('f2')))
    ).rejects.toThrow('f2');

    expect(breaker.getState().state).toBe('open');

    // Advance time past the timeout
    vi.setSystemTime(new Date(2024, 0, 1, 12, 0, 2));

    // Now the next call should transition to half-open and succeed
    const result = await breaker.call(() => Promise.resolve('recovered'));
    expect(result).toBe('recovered');
    expect(breaker.getState().state).toBe('closed');

    vi.useRealTimers();
  });

  it('resets failure count on successful call', async () => {
    const breaker = createCircuitBreaker(2);

    await expect(
      breaker.call(() => Promise.reject(new Error('fail')))
    ).rejects.toThrow('fail');

    expect(breaker.getState().failures).toBe(1);

    await breaker.call(() => Promise.resolve('ok'));
    expect(breaker.getState().failures).toBe(0);
  });
});