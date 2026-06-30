# Runtime Library Integration Patterns

This document provides patterns for integrating new runtime modules with the existing Sovereign Studio runtime library.

## Existing Runtime Files

The runtime library in `src/features/product/runtime/` contains shared utilities used across the application. Key files include:

| File | Purpose |
|------|---------|
| `quietInspectorHintPolicy.ts` | Unified signal format for inspectors |
| `runtimeInspectorRuntime.ts` | Existing inspector state builder |
| `androidQuickInteractionRuntime.ts` | Haptics, clipboard, URL detection |
| `devChatWorkerBridge.ts` | Worker communication |
| `builderContainerRuntime.ts` | Container state derivation |

## Signal Contract

When creating inspector panels that display runtime state, follow the unified signal format:

### Basic Signal Structure

```typescript
interface RuntimeInspectorSignal {
  readonly id: string;           // Unique identifier (e.g., "pat-count")
  readonly label: string;         // Short display (e.g., "Pattern Memory")
  readonly detail: string;       // Descriptive text (e.g., "5 Einträge gespeichert")
  readonly prompt: string;       // Action text for composer fill
  readonly lamp: QuietInspectorLamp;  // Visual state: "green" | "yellow" | "red"
  readonly targetTab: QuietInspectorTarget;  // Navigation target
}
```

### QuietInspectorSignal Format

For integration with the unified inspector system:

```typescript
interface QuietInspectorSignal {
  readonly id: string;
  readonly source: string;
  readonly lamp: QuietInspectorLamp;
  readonly message: string;
  readonly targetTab: QuietInspectorTarget;
  readonly visible?: boolean;
  readonly updatedAt?: number;
}
```

### Conversion Helper Pattern

Always export a conversion function to bridge your signals to the unified format:

```typescript
import { type QuietInspectorSignal, type QuietInspectorLamp, type QuietInspectorTarget } from "./quietInspectorHintPolicy";

export function toQuietInspectorSignal(
  signal: MyModuleSignal,
  source: string
): QuietInspectorSignal {
  return {
    id: signal.id,
    source,
    lamp: signal.lamp,
    message: `${signal.label}: ${signal.detail}`,
    targetTab: signal.targetTab,
    visible: true,
    updatedAt: Date.now(),
  };
}
```

## Android Interaction Helpers

For mobile-specific features, use the guarded helpers:

### Haptic Feedback

```typescript
import { triggerAndroidHaptic } from "./androidQuickInteractionRuntime";

// Always guard against undefined navigator
const triggerHaptic = (type: 'light' | 'medium' | 'heavy' = 'light') => {
  triggerAndroidHaptic(typeof navigator === "undefined" ? undefined : navigator, type);
};
```

### Clipboard Operations

```typescript
import { copyAndroidBubbleText } from "./androidQuickInteractionRuntime";

const handleCopy = async (text: string) => {
  await copyAndroidBubbleText(text, typeof navigator === "undefined" ? undefined : navigator);
};
```

### Follow-up Draft Creation

```typescript
import { createAndroidFollowUpDraft } from "./androidQuickInteractionRuntime";

const handleFollowUp = (bubbleText: string) => {
  const draft = createAndroidFollowUpDraft(bubbleText);
  if (draft) setWishText(draft);  // Only mutates composer
};
```

### URL Detection

```typescript
import { detectAndroidQuickRepoUrl } from "./androidQuickInteractionRuntime";

// Use in composer route hint
const quickRepo = detectAndroidQuickRepoUrl(clean);
if (quickRepo.recognized) return quickRepo.hint;
```

## BuilderContainer Integration Pattern

When adding features to BuilderContainer.tsx:

### 1. Import Runtime Helpers

```typescript
import {
  deriveRuntimeInspectorSignals,
  type RuntimeInspectorSignal,
} from "../runtime/runtimeInspectorPanelRuntime";
```

### 2. Wire Signals to Components

```typescript
<ModuleScreen
  inspectorSignals={deriveRuntimeInspectorSignals(
    activeMod.id.toUpperCase() as "PAT" | "ORC" | "INT",
    { hasMemory: palDecisions.length > 0, patternCount: palDecisions.length },
    { /* orc state */ },
    { chatRepoSnapshot },
  )}
  onSignalClick={(prompt) => setWishText(prompt)}
/>
```

### 3. Long-Press Menu Pattern

```typescript
// In Bubble component
const handleCopy = async () => {
  await copyAndroidBubbleText(msg.text, typeof navigator === "undefined" ? undefined : navigator);
  setShowMenu(false);
  triggerAndroidHaptic(typeof navigator === "undefined" ? undefined : navigator, "light");
};

const handleFollowUp = () => {
  const draft = createAndroidFollowUpDraft(msg.text);
  if (draft) onLongPress?.(draft);
  setShowMenu(false);
  triggerAndroidHaptic(typeof navigator === "undefined" ? undefined : navigator, "light");
};
```

## Testing Patterns

### Runtime Module Tests

```typescript
import { describe, expect, it } from "vitest";
import { deriveMySignals } from "./myModuleRuntime";

describe("myModuleRuntime", () => {
  it("returns honest empty state when no data", () => {
    const signals = deriveMySignals({ /* empty state */ });
    expect(signals).toHaveLength(1);
    expect(signals[0].lamp).toBe("yellow");  // Empty = yellow
  });

  it("includes lamp and targetTab for inspector integration", () => {
    const signals = deriveMySignals({ /* data */ });
    signals.forEach((s) => {
      expect(s.lamp).toBeTruthy();
      expect(s.targetTab).toBeTruthy();
    });
  });

  it("signal prompts do not contain auto-send keywords", () => {
    const signals = deriveMySignals({ /* data */ });
    signals.forEach((s) => {
      expect(s.prompt).not.toMatch(/submit|send|enter/i);
    });
  });
});
```

### Integration with quietInspectorHintPolicy

```typescript
describe("toQuietInspectorSignal", () => {
  it("converts RuntimeInspectorSignal to QuietInspectorSignal format", () => {
    const signal = deriveMySignals({ /* data */ })[0];
    const quiet = toQuietInspectorSignal(signal, "my-source");
    
    expect(quiet.id).toBe(signal.id);
    expect(quiet.source).toBe("my-source");
    expect(quiet.lamp).toBe(signal.lamp);
    expect(quiet.message).toBe(`${signal.label}: ${signal.detail}`);
  });
});
```

## State Derivation Patterns

### Empty State → Yellow Lamp

```typescript
export function deriveMySignals(state: MyState): RuntimeInspectorSignal[] {
  if (!state.hasData) {
    return [{
      id: "my-empty",
      label: "My Feature",
      detail: "No data visible.",
      prompt: "Explain the current state.",
      lamp: "yellow" as const,
      targetTab: "my-tab" as const,
    }];
  }
  // ... return green lamp signals for actual data
}
```

### Truncated State → Yellow Lamp

```typescript
// For repo snapshots
export function deriveIntInspectorSignals(state: IntState): RuntimeInspectorSignal[] {
  // ...
  signals.push({
    id: "int-files",
    label: "Dateien",
    detail: `${count} Dateien${snapshot.truncated ? " (gekürzt)" : ""}`,
    lamp: snapshot.truncated ? ("yellow" as const) : ("green" as const),
    targetTab: "repo" as const,
  });
}
```

### Count-Based Signals

```typescript
export function deriveOrcInspectorSignals(state: OrcState): RuntimeInspectorSignal[] {
  if (state.palDecisions === 0) {
    return [{ /* empty state with yellow lamp */ }];
  }
  
  const signals: RuntimeInspectorSignal[] = [];
  
  if (state.fastTierCount > 0) {
    signals.push({
      id: "orc-fast",
      label: "Fast Tier",
      detail: `${state.fastTierCount} Entscheidungen`,
      // NO percentage - counts only
      lamp: "green" as const,
      targetTab: "runtime" as const,
    });
  }
  
  return signals;
}
```

## Anti-Patterns to Avoid

1. **No hardcoded percentages** — Use counts, not percentages
2. **No fake success states** — Only show green when data is actually present
3. **No auto-submit from UI** — Always let user confirm
4. **No hidden metadata in copy** — Only copy visible text
5. **No direct state mutation** — Follow the causal chain
6. **No percentage in routing stats** — Show counts by tier, not ratios
