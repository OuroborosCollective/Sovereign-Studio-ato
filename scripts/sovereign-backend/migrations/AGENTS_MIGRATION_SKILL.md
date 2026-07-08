# Database Migration - Skill Guide

> **Für AI-Agenten**: Pattern für PostgreSQL Migrations im Sovereign Studio Backend.

---

## 🎯 Ziel

Sichere, idempotente Migrationen erstellen die:
- Mehrfach ausführbar sind
- Neue Tabellen/Spalten hinzufügen
- Indizes und Constraints definieren
- VPS-Container kompatibel sind

---

## 📝 Migration Template

```sql
-- scripts/sovereign-backend/migrations/XXX_description.sql
-- Migration: XXX_description
-- Description: What this migration does
-- Created: YYYY-MM-DD

-- ============================================
-- Add columns to existing tables
-- ============================================
ALTER TABLE table_name 
ADD COLUMN IF NOT EXISTS new_column TYPE DEFAULT value;

-- ============================================
-- Create new tables
-- ============================================
CREATE TABLE IF NOT EXISTS new_table (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Foreign keys
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT unique_name UNIQUE (name),
    CONSTRAINT positive_value CHECK (value > 0)
);

-- ============================================
-- Create indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_table_column 
ON table_name(column);

CREATE INDEX IF NOT EXISTS idx_table_composite 
ON table_name(column1, column2) 
WHERE column1 IS NOT NULL;

-- ============================================
-- Add JSONB columns for flexible data
-- ============================================
ALTER TABLE table_name 
ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- ============================================
-- Add enum types
-- ============================================
DO $$ BEGIN
    CREATE TYPE status_type AS ENUM ('pending', 'active', 'completed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- ============================================
-- Migration record (if using schema_migrations table)
-- ============================================
-- INSERT INTO schema_migrations (version, applied_at)
-- VALUES ('XXX', NOW())
-- ON CONFLICT (version) DO NOTHING;

-- ============================================
-- Output
-- ============================================
DO $$
BEGIN
    RAISE NOTICE 'Migration XXX completed successfully';
    RAISE NOTICE 'Changes: Describe changes here';
END $$;
```

---

## 🐳 VPS Deployment via stdin

```python
# Paramiko mit stdin - wichtig für Container!
import paramiko

def apply_migration(host, sql_content, db="postgres"):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="root", password="PASS")
    
    # Command mit -i für stdin
    cmd = f"docker exec -i supabase-db psql -U postgres -d {db}"
    
    transport = ssh.get_transport()
    channel = transport.open_session()
    channel.exec_command(cmd)
    
    # SQL senden
    channel.send(sql_content.encode())
    channel.shutdown_write()
    
    # Output lesen
    stdout = b""
    stderr = b""
    while True:
        if channel.recv_ready():
            stdout += channel.recv(4096)
        if channel.recv_stderr_ready():
            stderr += channel.recv_stderr(4096)
        if channel.exit_status_ready():
            break
    
    ssh.close()
    
    return stdout.decode(), stderr.decode()
```

---

## ⚠️ Häufige Fehler

### 1. IF NOT EXISTS vergessen
```sql
-- ❌ FALSCH: Fehler bei wiederholter Ausführung
CREATE TABLE new_table (...);

-- ✅ RICHTIG: Idempotent
CREATE TABLE IF NOT EXISTS new_table (...);
```

### 2. psql im Container mit -f
```bash
# ❌ FALSCH: Datei existiert nicht im Container
docker exec db psql -f /tmp/migration.sql

# ✅ RICHTIG: Via stdin
docker exec -i db psql -f /dev/stdin < migration.sql
# Oder mit paramiko channel.send()
```

### 3. Constraint ohne IF NOT EXISTS
```sql
-- ❌ FALSCH
ALTER TABLE t ADD CONSTRAINT c CHECK (value > 0);

-- ✅ RICHTIG
DO $$ BEGIN
    ALTER TABLE t ADD CONSTRAINT c CHECK (value > 0);
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
```

---

## 🔍 Verification Queries

```sql
-- Prüfe ob Tabelle existiert
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'table_name'
);

-- Prüfe ob Spalte existiert
SELECT EXISTS (
    SELECT FROM information_schema.columns 
    WHERE table_name = 'table_name' 
    AND column_name = 'column_name'
);

-- Liste alle sovereign_agent Tabellen
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name LIKE 'sovereign_agent_%';
```

---

## 📋 Checklist

- [ ] `IF NOT EXISTS` für Tabellen
- [ ] `IF NOT EXISTS` für Indizes
- [ ] `DO $$ ... EXCEPTION ... END $$` für Constraints
- [ ] `ON CONFLICT DO NOTHING` für Insert
- [ ] `RAISE NOTICE` für Feedback
- [ ] Test auf lokaler DB
- [ ] Verification Query nach Deployment

---

*Last Updated: 2026-07-08*
