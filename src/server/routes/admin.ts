/**
 * Admin API contract — type re-exports for the sovereign-backend.
 *
 * The real backend runs at https://sovereign-backend.arelorian.de
 * Source: /opt/sovereign-backend/app.py  (Flask + PostgreSQL)
 *
 * Frontend callers: src/features/admin/api/adminApiClient.ts
 *
 * Issue #460
 */

// Re-export all types from the real API client so any legacy import still resolves.
export type {
  UserRole,
  SubscriptionStatus,
  AdminUser,
  Transaction,
  BillingStats,
  LauncherToolOverride,
  LlmRoute,
  AuditEntry,
} from '../../features/admin/api/adminApiClient';
