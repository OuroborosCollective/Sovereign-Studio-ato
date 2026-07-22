import { describe, expect, it } from 'vitest';

import { normalizeTransaction } from '../api/adminApiClient';
import { finiteTransactionAmount } from './TransactionTable';

const baseTransaction = {
  id: 'transaction-1',
  userId: 'user-1',
  userEmail: 'admin@example.invalid',
  type: 'subscription' as const,
  currency: 'EUR',
  status: 'completed' as const,
  description: 'Test subscription',
  createdAt: '2026-07-22T12:00:00Z',
};

describe('admin transaction amount contract', () => {
  it('normalizes PostgreSQL NUMERIC JSON strings before rendering', () => {
    const transaction = normalizeTransaction({
      ...baseTransaction,
      amount: '9.99',
    });

    expect(transaction.amount).toBe(9.99);
    expect(finiteTransactionAmount(transaction.amount)).toBe(9.99);
  });

  it('fails safely instead of throwing for malformed legacy values', () => {
    const transaction = normalizeTransaction({
      ...baseTransaction,
      amount: 'not-a-number',
    });

    expect(transaction.amount).toBe(0);
    expect(finiteTransactionAmount('not-a-number')).toBeNull();
    expect(finiteTransactionAmount(null)).toBe(0);
  });
});
