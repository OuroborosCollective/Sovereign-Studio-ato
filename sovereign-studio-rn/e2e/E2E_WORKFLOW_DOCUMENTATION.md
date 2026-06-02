# E2E Testing & Auto-Fix Workflow Documentation
## Sovereign Studio React Native Expo App

---

## 📋 Overview

This document describes the comprehensive E2E testing infrastructure created for the React Native Expo app (`sovereign-studio-rn/`). The workflow provides enterprise-grade testing with automatic failure recovery and self-healing capabilities.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     E2E Testing Pipeline                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Detox  │───▶│ API Fall │───▶│ Auto-Fix │───▶│Self-Heal │  │
│  │   E2E   │    │back Chain│    │   Loop   │    │   Loop   │  │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘  │
│       │               │               │               │        │
│       └───────────────┴───────────────┴───────────────┘        │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │  N8n-style  │                              │
│                    │  Workflows  │                              │
│                    └─────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🧪 Test Suites

### 1. Detox E2E Tests (`e2e/detox/`)

**Purpose**: Real device testing for Android/iOS

**Features**:
- Screen navigation testing
- User interaction flows
- State management validation
- AI integration testing
- GitHub integration testing

**Files**:
- `app.spec.ts` - Main test suite
- `jest.config.js` - Test configuration

**Run**:
```bash
npm run e2e:detox
```

### 2. API Fallback Tests (`e2e/api-fallback/`)

**Purpose**: Multi-provider AI fallback chain testing

**Providers**:
1. **MLVoca** (Primary) - `https://api.mlvoca.com/v1`
2. **P8lination** (Secondary) - `https://api.p8lination.io/v1`
3. **Gemini** (Tertiary) - `https://generativelanguage.googleapis.com/v1beta`
4. **Groq** (Fallback) - `https://api.groq.com/openai/v1`

**Features**:
- Health check tests
- Fallback chain tests
- Latency tests
- Circuit breaker tests
- Error recovery tests

**Run**:
```bash
npm run e2e:api-fallback
```

### 3. Self-Healing Tests (`e2e/self-healing/`)

**Purpose**: Automatic recovery and fault tolerance

**Recovery Strategies**:
1. Reload React Native
2. Clear App State
3. Reset Network
4. Fallback to Cache
5. Restart App
6. Send to Background
7. Factory Reset

**Features**:
- Recovery strategy tests
- Healing loop tests
- Health monitoring tests
- Fault tolerance tests

**Run**:
```bash
npm run e2e:self-healing
```

### 4. N8n-style Workflows (`e2e/workflows/`)

**Purpose**: Automation workflows for GitHub, code generation, and testing

**Workflows**:
1. **E2E Test Trigger** - Trigger tests on PR/push
2. **Auto-Fix Loop** - Auto-fix test failures
3. **GitHub Integration** - Process PRs and comments
4. **Code Generation** - AI-powered code generation
5. **API Fallback** - Handle API failures gracefully

**Run**:
```bash
npm run workflow:execute
```

---

## 🔄 Auto-Fix Loop (Unlimited Iterations)

The auto-fix loop implements the following cycle and **runs until all tests pass**:

```
Test Fail ──▶ Analyze Error ──▶ Generate Fix ──▶ Apply Fix ──▶ Re-Test
     │              │               │             │            │
     └──────────────┴───────────────┴─────────────┴────────────┘
                         (Until Pass - Unlimited Iterations)
```

### Configuration

| Parameter | Default | Description |
|-----------|--------|-------------|
| `maxIterations` | **∞ (Infinity)** | Unlimited - keeps trying until all tests pass |
| `testCommand` | `npm run e2e:detox` | Test command to run |
| `fixModel` | `gemini` | AI model for fix generation |
| `autoMerge` | false | Auto-merge on success |
| `verbose` | true | Log all operations |

### Unlimited Mode

**Self-Healing Loop**: Runs infinitely until:
- ✅ All tests pass
- ⏱️ GitHub Actions timeout (6 hours)
- 💥 Unrecoverable error

### Usage

```bash
# Run auto-fix with unlimited iterations (default)
npx ts-node e2e/auto-fix/auto-fix-loop.ts

# Custom configuration (still unlimited)
npx ts-node e2e/auto-fix/auto-fix-loop.ts --max=Infinity --test=detox --verbose
```

---

## 🚀 CI Integration

### GitHub Actions Workflow

**Trigger**: Push/PR to `main`, `develop`, or `feature/**`

**Jobs**:
1. `setup` - Environment preparation
2. `detox-e2e` - Device tests
3. `api-fallback-tests` - API chain tests
4. `self-healing-tests` - Recovery tests
5. `auto-fix` - Auto-fix on failure
6. `merge-check` - PR readiness check
7. `publish-results` - Summary report

### Secrets Required

| Secret | Description |
|--------|-------------|
| `MLVOCA_API_KEY` | MLVoca API key |
| `P8LINATION_API_KEY` | P8lination API key |
| `GEMINI_API_KEY` | Gemini API key |
| `GROQ_API_KEY` | Groq API key |

### Workflow Dispatch

```bash
# Run all tests
gh workflow run e2e-testing.yml

# Run specific suite
gh workflow run e2e-testing.yml -f test_suite=detox

# Enable auto-fix
gh workflow run e2e-testing.yml -f auto_fix=true
```

---

## 📁 Directory Structure

```
sovereign-studio-rn/
├── e2e/
│   ├── README.md
│   ├── jest.config.ts
│   ├── run-e2e.ts
│   ├── config/
│   │   ├── detox.config.ts
│   │   └── workflow.config.ts
│   ├── detox/
│   │   └── app.spec.ts
│   ├── api-fallback/
│   │   ├── api-fallback.config.ts
│   │   └── api-fallback.spec.ts
│   ├── self-healing/
│   │   ├── self-healing.config.ts
│   │   └── self-healing.spec.ts
│   ├── workflows/
│   │   ├── workflow.config.ts
│   │   └── workflow.spec.ts
│   └── auto-fix/
│       └── auto-fix-loop.ts
├── scripts/
│   ├── run-e2e.js
│   └── workflow-executor.js
└── package.json (scripts added)
```

---

## 🔧 Configuration Files

### Detox Configuration

```typescript
// e2e/config/detox.config.ts
export default {
  testRunner: {
    args: { '$0': 'jest', config: 'e2e/detox/jest.config.js' },
  },
  behavior: { reuse: true },
  configurations: {
    'android.debug': {
      type: 'android.attached',
      binaryPath: 'android/app/build/outputs/apk/debug/app-debug.apk',
    },
  },
};
```

### API Fallback Configuration

```typescript
// e2e/api-fallback/api-fallback.config.ts
export const FALLBACK_CONFIG = {
  providers: [mlvoca, p8lination, gemini, groq],
  maxRetries: 5,
  circuitBreakerThreshold: 5,
  healthCheckInterval: 60000,
};
```

### Workflow Configuration

```typescript
// e2e/workflows/workflow.config.ts
export const WORKFLOW_EXECUTOR_CONFIG = {
  maxConcurrentWorkflows: 5,
  maxRetries: 3,
  timeout: 300000,
  retryDelay: 5000,
};
```

---

## 📊 Test Metrics

### Coverage Targets

| Metric | Target |
|--------|--------|
| Test Coverage | 70% |
| API Fallback Success | 95% |
| Self-Healing Success | 90% |
| Auto-Fix Success | 80% |

### Performance Targets

| Test Type | Target Latency |
|-----------|----------------|
| MLVoca | 5s |
| P8lination | 10s |
| Gemini | 15s |
| Groq | 8s |

---

## 🛠️ Development Commands

```bash
# Run all E2E tests
npm run e2e:all

# Run specific test suites
npm run e2e:detox
npm run e2e:api-fallback
npm run e2e:self-healing
npm run e2e:auto-fix

# Run with CI mode
npm run e2e:ci

# Execute workflows
npm run workflow:execute
npm run workflow:e2e-trigger
npm run workflow:auto-fix
```

---

## 🔐 Security Considerations

1. **API Keys**: Stored as GitHub secrets
2. **Token Rotation**: Implemented for all providers
3. **Circuit Breaker**: Prevents cascade failures
4. **Timeout Handling**: Graceful degradation
5. **Error Logging**: Secure logging without secrets

---

## 📚 Additional Resources

- [Detox Documentation](https://wix.github.io/Detox/)
- [Jest Testing](https://jestjs.io/)
- [React Native Testing](https://reactnative.dev/docs/testing-overview)
- [GitHub Actions](https://docs.github.com/en/actions)

---

*Generated by OpenHands for Sovereign Studio*
*Last Updated: 2026-06-02*