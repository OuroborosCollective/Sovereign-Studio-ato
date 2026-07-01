---
name: Payment module — Sovereign Studio V3
description: Zahlungsmodul mit PayPal, Skrill, Crypto, Google Play IAP — DB-Schema, Backend-Routen, Admin-UI. Commit ee4961fe auf main, Issues #457 + #456 geschlossen.
---

# Payment Module

## Datenbank-Schema (muss einmalig auf dem Postgres-Server ausgeführt werden)

```sql
CREATE TABLE IF NOT EXISTS payment_methods (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type       VARCHAR(50) UNIQUE NOT NULL,
  label      TEXT NOT NULL,
  enabled    BOOLEAN NOT NULL DEFAULT false,
  config     JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS credit_packages (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  credits     INTEGER NOT NULL,
  price_eur   NUMERIC(10,2) NOT NULL,
  description TEXT,
  enabled     BOOLEAN NOT NULL DEFAULT true,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Nach Migration im Admin-Panel: Tab "Zahlungen" → "Standard-Methoden anlegen" klicken.

## Backend-Routen (alle in scripts/sovereign-backend/app.py)

**Admin (Bearer-Auth):**
- `GET  /api/admin/payment-methods` — alle Methoden
- `PATCH /api/admin/payment-methods/<id>` — enabled/label/config ändern
- `POST /api/admin/payment-methods/init` — Standard-Methoden anlegen (idempotent)
- `GET  /api/admin/credit-packages` — alle Pakete
- `POST /api/admin/credit-packages/init` — Standard-Pakete anlegen
- `PATCH /api/admin/credit-packages/<id>` — Paket bearbeiten
- `POST /api/admin/payment-methods/crypto/confirm` — Crypto-Zahlung manuell bestätigen

**Öffentlich / User:**
- `GET  /api/billing` — Pakete + Subscription
- `GET  /api/billing/payment-methods` — aktivierte Methoden (kein Secret)
- `POST /api/billing/purchase` — generischer Dispatcher (paymentMethod im Body)
- `POST /api/billing/purchase/paypal/create-order` — PayPal Order erstellen
- `POST /api/billing/purchase/paypal/capture` — PayPal Order capture
- `POST /api/billing/webhooks/paypal` — PayPal IPN
- `POST /api/billing/purchase/skrill/init` — Skrill Redirect-URL
- `POST /api/billing/webhooks/skrill` — Skrill IPN (MD5 verifiziert)
- `POST /api/billing/purchase/crypto/info` — Wallet-Adresse + EUR-Betrag
- `POST /api/billing/purchase/google-play/validate` — Google Play IAP Validierung

## Frontend

- `PaymentMethodEditor.tsx` — Admin-Tab mit Toggle + Credential-Formular pro Methode
- `adminApiClient.ts` — PaymentMethod, CreditPackage Typen + alle API-Calls
- `useAdminApi.ts` — `useAdminPaymentMethods` Hook
- `AdminPanel.tsx` — Tab "Zahlungen" (Wallet-Icon), Tab-Typ erweitert
- `billingSlice.ts` — `purchasePackage` akzeptiert `string | PurchaseArgs`,
  neue Thunks: `capturePayPalOrder`, `fetchEnabledPaymentMethods`

## Wichtige Entscheidungen

**Why config in DB:** Credentials werden in der `payment_methods.config` JSONB-Spalte gespeichert — kein Hardcode, kein Env-Var-Chaos. Admin trägt sie über die UI ein.

**Crypto ist manuell:** Kein On-Chain-Watch — Admin bestätigt nach Eingang via `/api/admin/payment-methods/crypto/confirm`. Das ist bewusst so, da Blockchain-APIs externe Keys brauchen.

**Google Play IAP:** Erfordert `cryptography`-Paket auf dem Server (JWT-Signatur für Service Account). Falls nicht installiert: HTTP 503 mit klarem Fehler.

**PayPal mode:** `live` oder `sandbox` — admin setzt via config.mode.
