# Sovereign LLM Proxy - Cloudflare Workers AI

Ein Cloudflare Worker AI Proxy für den LLM-Router. Nutzt direkt die Cloudflare Service Token Authentifizierung.

## Features

- ✅ **OpenAI-kompatibles API** - `/v1/chat/completions` Endpunkt
- ✅ **Cloudflare Service Token Auth** - Nutzt CF_AI_TOKEN direkt
- ✅ **Cloudflare Workers AI Integration** - Zugriff auf alle Cloudflare AI Modelle
- ✅ **Rate Limiting** - Inklusive In-Memory Store (KV für Produktion empfohlen)
- ✅ **Model Whitelisting** - Optionale Einschränkung erlaubter Modelle
- ✅ **Telemetry** - Response-Time und Request-Tracking

## API Endpunkt

```
POST /v1/chat/completions
```

### Headers

```
Content-Type: application/json
```

### Request Body

```json
{
  "model": "@cf/meta/llama-3-8b-instruct",
  "messages": [
    {"role": "system", "content": "Du bist ein hilfreicher Assistent."},
    {"role": "user", "content": "Erkläre mir Cloudflare Workers."}
  ],
  "temperature": 0.7,
  "max_tokens": 1000
}
```

### Response

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "@cf/meta/llama-3-8b-instruct",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Antwort des Modells..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 150,
    "total_tokens": 200
  }
}
```

## Deployment

### 1. Wrangler CLI installieren

```bash
npm install -g wrangler
```

### 2. Authentifizieren

```bash
wrangler login
```

### 3. Secrets konfigurieren

```bash
# Cloudflare AI Token (von Cloudflare Dashboard)
wrangler secret put CF_AI_TOKEN
# Wert: <DEIN_CF_AI_TOKEN>

# Cloudflare Account ID
wrangler secret put CF_ACCOUNT_ID
# Wert: <DEIN_CF_ACCOUNT_ID>

# Optional: Rate Limit (requests:windowMs)
# Standard: 100:60000 (100 requests pro Minute)
```

### 4. Optionale Konfiguration

```bash
# Erlaubte Modelle (kommasepariert)
wrangler secret put ALLOWED_MODELS
# Wert: @cf/meta/llama-3-8b-instruct,@cf/meta/llama-3-70b-instruct

# Rate Limit
wrangler secret put RATE_LIMIT
# Wert: 100:60000 (100 requests pro Minute)

# Default Model
wrangler secret put DEFAULT_MODEL
# Wert: @cf/meta/llama-3-8b-instruct
```

### 5. Deployen

```bash
cd cloudflare-worker-ai-proxy
npm install
npm run deploy
```

### 6. Worker URL merken

Nach dem Deployment erhältst du eine URL wie:
```
https://sovereign-llm-proxy.<deine-subdomain>.workers.dev
```

## Environment Variables (wrangler secret)

| Variable | Erforderlich | Beschreibung |
|----------|--------------|--------------|
| `CF_AI_TOKEN` | ✅ | Cloudflare AI API Token |
| `CF_ACCOUNT_ID` | ✅ | Cloudflare Account ID |
| `ALLOWED_MODELS` | ❌ | Erlaubte Modelle (kommasepariert) |
| `DEFAULT_MODEL` | ❌ | Default Modell |
| `RATE_LIMIT` | ❌ | Rate Limit (format: requests:windowMs) |

## Verfügbare Modelle

Cloudflare Workers AI unterstützt verschiedene Modelle:

- `@cf/meta/llama-3-8b-instruct` - Meta Llama 3 8B
- `@cf/meta/llama-3-70b-instruct` - Meta Llama 3 70B
- `@cf/anthropic/claude-3-sonnet` - Claude 3 Sonnet
- `@cf/google/gemma-2-2b-it` - Google Gemma 2 2B
- `@cf/deepseek-ai/deepseek-coder-6.7b` - Deepseek Coder
- `@cf/qwen/qwen-1.8b-chat` - Qwen 1.8B Chat

## Monitoring

```bash
# Live Logs anzeigen
npm run tail
```

## Sovereign Studio Integration

In deiner Sovereign Studio `.env` Datei:

```env
VITE_SOVEREIGN_LLM_PROXY_URL=https://sovereign-llm-proxy.<deine-subdomain>.workers.dev
```

## Sicherheit

- ❌ **Nie** URL Secrets in Code committen
- ❌ **Nie** API Tokens in öffentlichen Repos teilen
- ✅ Secrets immer über `wrangler secret put` setzen
- ✅ Regelmäßig Secrets rotieren
