# React Native E2E Testing & Auto-Fix Workflow
# Sovereign Studio - Comprehensive Testing Infrastructure

## Overview

This workflow provides a complete E2E testing pipeline for the React Native Expo app with:
- **Detox E2E Tests** - Real device testing
- **API Fallback Chain** - MLVoca → P8lination → Gemini → Groq
- **N8n-like Features** - GitHub Integration, Code Generation, Workflows
- **Auto-Fix Loop** - Error → Fix → Re-Test → Auto-Merge
- **Self-Healing** - Continuous healing until all tests pass

## Architecture

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

## Test Categories

### 1. Detox E2E Tests (`e2e/detox/`)
- Real device simulation
- User interaction flows
- Navigation testing
- State management validation

### 2. API Fallback Tests (`e2e/api-fallback/`)
- MLVoca (Primary)
- P8lination (Secondary)
- Gemini (Tertiary)
- Groq (Fallback)

### 3. Self-Healing Tests (`e2e/self-healing/`)
- Automatic error recovery
- Component re-rendering
- State restoration
- Memory leak detection

### 4. Integration Tests
- GitHub API integration
- Code generation workflows
- Canvas operations
- Matrix chat functionality

## Auto-Fix Loop

```
Test Fail ──▶ Analyze Error ──▶ Generate Fix ──▶ Apply Fix ──▶ Re-Test
     │              │               │             │            │
     └──────────────┴───────────────┴─────────────┴────────────┘
                         (Until Pass or Max Attempts)
```

## Configuration

All configurations are managed in `e2e/config/`:
- `detox.config.ts` - Detox test configuration
- `api-fallback.config.ts` - API fallback chain settings
- `self-healing.config.ts` - Self-healing parameters
- `workflow.config.ts` - N8n-style workflow definitions

## Usage

```bash
# Run all E2E tests
npm run e2e:all

# Run specific test suite
npm run e2e:detox
npm run e2e:api-fallback
npm run e2e:self-healing

# Run auto-fix loop
npm run e2e:auto-fix

# Run with CI mode (auto-merge on success)
npm run e2e:ci
```

## CI Integration

The workflow integrates with GitHub Actions via `.github/workflows/`:
- Pull request testing
- Auto-comment on failures
- Auto-merge on success
- Slack notifications

## Metrics

- Test coverage
- Failure rate
- Average fix time
- Self-healing success rate
- API fallback statistics