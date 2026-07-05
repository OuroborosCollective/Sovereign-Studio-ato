#!/usr/bin/env python3
"""
Database Migration Script for Issue #516 - Admin Runtime

Creates:
1. admin_api_keys - Maps API keys to admin users for audit trail
2. credit_ledger - Append-only credit transaction log

Run this after deploying the new code:
    python3 scripts/sovereign-backend/migrations/migrate.py

The migration preserves existing admin_users.credits by reconciling them into
append-only ledger rows before syncing the cached balance from the ledger sum.
"""
import os
import sys

import psycopg2


def get_db_connection():
    """Create database connection from environment variables."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "host.docker.internal"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def run_migration(conn):
    """Run the migration."""
    print("Starting migration: admin_api_keys and credit_ledger tables...")

    cur = conn.cursor()

    print("\n1. Creating admin_api_keys table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_api_keys (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            admin_id        UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
            key_hash        TEXT        UNIQUE NOT NULL,
            label           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_used_at    TIMESTAMPTZ
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_api_keys_key_hash ON admin_api_keys(key_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_api_keys_admin_id ON admin_api_keys(admin_id)")
    print("   ✓ admin_api_keys table ready")

    print("\n2. Creating credit_ledger table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS credit_ledger (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
            type            VARCHAR(50) NOT NULL,
            amount          INTEGER     NOT NULL,
            reason          TEXT,
            provider        TEXT,
            provider_tx_id  TEXT,
            created_by      UUID        REFERENCES admin_users(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_id ON credit_ledger(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_credit_ledger_created_at ON credit_ledger(created_at DESC)")
    print("   ✓ credit_ledger table ready")

    print("\n3. Syncing existing transactions to ledger...")
    cur.execute("""
        INSERT INTO credit_ledger (user_id, type, amount, reason, created_at)
        SELECT
            user_id,
            CASE
                WHEN type = 'adjustment' AND COALESCE(amount, 0) > 0 THEN 'bonus'
                WHEN type = 'adjustment' AND COALESCE(amount, 0) < 0 THEN 'correction'
                ELSE COALESCE(type, 'purchase')
            END,
            COALESCE(amount, 0),
            description,
            created_at
        FROM transactions t
        WHERE user_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM credit_ledger l
              WHERE l.created_at = t.created_at
                AND l.user_id = t.user_id
                AND l.reason IS NOT DISTINCT FROM t.description
          )
          AND type IN ('purchase', 'adjustment', 'refund', 'chargeback', 'bonus', 'spend')
    """)
    synced = cur.rowcount
    print(f"   ✓ Synced {synced} existing transactions to ledger")

    print("\n4. Reconciling legacy cached credits into ledger...")
    cur.execute("""
        INSERT INTO credit_ledger (user_id, type, amount, reason, created_at)
        SELECT
            au.id,
            'opening_balance',
            au.credits,
            'Opening balance created by Issue #516 migration from legacy admin_users.credits',
            NOW()
        FROM admin_users au
        WHERE au.credits > 0
          AND NOT EXISTS (
              SELECT 1 FROM credit_ledger cl
              WHERE cl.user_id = au.id
          )
    """)
    opening_rows = cur.rowcount
    print(f"   ✓ Created {opening_rows} opening balance ledger entries")

    cur.execute("""
        INSERT INTO credit_ledger (user_id, type, amount, reason, created_at)
        SELECT
            au.id,
            'migration_reconciliation',
            au.credits - COALESCE(ledger.balance, 0),
            'Migration reconciliation to preserve legacy admin_users.credits',
            NOW()
        FROM admin_users au
        LEFT JOIN (
            SELECT user_id, COALESCE(SUM(amount), 0) AS balance
            FROM credit_ledger
            GROUP BY user_id
        ) ledger ON ledger.user_id = au.id
        WHERE au.credits > COALESCE(ledger.balance, 0)
          AND NOT EXISTS (
              SELECT 1 FROM credit_ledger cl
              WHERE cl.user_id = au.id
                AND cl.type = 'migration_reconciliation'
          )
    """)
    reconciliation_rows = cur.rowcount
    print(f"   ✓ Created {reconciliation_rows} reconciliation ledger entries")

    print("\n5. Creating credit recalculation function...")
    cur.execute("""
        CREATE OR REPLACE FUNCTION recalculate_user_credits(p_user_id UUID)
        RETURNS INTEGER AS $$
        DECLARE
            v_balance INTEGER;
        BEGIN
            SELECT COALESCE(SUM(amount), 0) INTO v_balance
            FROM credit_ledger
            WHERE user_id = p_user_id;

            UPDATE admin_users SET credits = GREATEST(0, v_balance)
            WHERE id = p_user_id;

            RETURN GREATEST(0, v_balance);
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)

    print("\n6. Syncing admin_users.credits cache with ledger...")
    cur.execute("""
        UPDATE admin_users au
        SET credits = GREATEST(0, ledger.balance)
        FROM (
            SELECT user_id, COALESCE(SUM(amount), 0) AS balance
            FROM credit_ledger
            GROUP BY user_id
        ) ledger
        WHERE au.id = ledger.user_id
    """)
    synced_users = cur.rowcount
    print(f"   ✓ Synced credits for {synced_users} users")

    conn.commit()

    print("\n7. Verification...")
    cur.execute("SELECT COUNT(*) FROM admin_api_keys")
    api_keys_count = cur.fetchone()[0]
    print(f"   - admin_api_keys: {api_keys_count} rows")

    cur.execute("SELECT COUNT(*) FROM credit_ledger")
    ledger_count = cur.fetchone()[0]
    print(f"   - credit_ledger: {ledger_count} rows")

    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT
                au.id,
                au.email,
                au.credits as cached_balance,
                COALESCE(SUM(cl.amount), 0) as ledger_balance
            FROM admin_users au
            LEFT JOIN credit_ledger cl ON cl.user_id = au.id
            GROUP BY au.id, au.email, au.credits
            HAVING au.credits != GREATEST(0, COALESCE(SUM(cl.amount), 0))
        ) mismatches
    """)
    mismatches = cur.fetchone()[0]

    if mismatches > 0:
        print(f"   ⚠️  Warning: {mismatches} users have mismatched credits!")
    else:
        print("   ✓ All user credits are consistent with ledger")

    print("\n✅ Migration completed successfully!")
    print("\nNext steps:")
    print("1. Create admin API keys for existing admins with the app endpoint or SQL.")
    print("2. Store only SHA256 hashes in admin_api_keys.key_hash, never raw keys.")
    return True


def main():
    """Main entry point."""
    print("=" * 60)
    print("Database Migration: Issue #516 - Admin Runtime")
    print("=" * 60)

    try:
        conn = get_db_connection()
        print(f"Connected to database: {os.getenv('POSTGRES_DB', 'postgres')}")
        run_migration(conn)
        conn.close()
        return 0
    except psycopg2.Error as e:
        print(f"\n❌ Database error: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
