# Sovereign Studio — Frontend Design Context

## Product thesis
Sovereign Studio is a truth-bound operator console, not a generic AI chat UI. The primary job is to let an owner dispatch a real repository mission, observe causal runtime readback, inspect workspace effects, and explicitly publish only after evidence is available.

## Audience and register
- Audience: technical owner/operator working on private repositories and runtime infrastructure.
- Register: authenticated product/admin console.
- Primary surface: Sovereign Control Surface vNext.
- Truth boundary: UI is a projection; runtime/readback remains authoritative.
- Visual metaphor: precision instrumentation — carbon panels, laser-red control marks, emerald evidence seals, and measured monospaced telemetry.

## Visual direction
**Signature:** a thin red causal spine visually ties command, live runtime, workspace and publication surfaces together. It represents flow, not decoration: command → execution → readback → publication.

The visual language should feel like an instrument built for operators, not a sci-fi game HUD. Use hard geometry, quiet surfaces, sparse glow, and high information density. Avoid gratuitous gradients, glassmorphism, giant rounded cards, or decorative dashboard widgets.

## Tokens

### Color
- Void: #050507 — application canvas and deepest runtime surfaces.
- Carbon: #0D0D11 — primary panel surface.
- Carbon Elevated: #1A1A22 — focused/raised controls.
- Laser Red: #FF1E38 — primary action, active boundary, execution signal.
- Pulse Red: #800016 — restrained action background.
- Emerald Seal: #10B981 — verified/readback-confirmed state.
- Amber Alert: #FF8C00 — caution, unavailable dependency, recoverable issue.
- Text Main: #F2F2F5 — primary content.
- Text Muted: #8B8B9E — secondary telemetry.
- Text Dim: #545465 — metadata and low-priority labels.

### Typography
- Display / navigation: system sans stack for reliable rendering and crisp small-screen density.
- Instrument / identifiers: JetBrains Mono → Fira Code → Roboto Mono → monospace.
- Body: system sans stack.
- Labels are sentence case where user-facing; telemetry may use uppercase because it is intentionally machine-oriented.
- Keep the type scale compact; hierarchy comes from weight, spacing and alignment before size.

### Geometry
- Primary control radius: 8–12px.
- Large container radius: 14–16px only where it clarifies grouping.
- Prefer clipped/diamond corners for instrument panels as a signature treatment.
- Keep borders thin and low-opacity; active boundaries use the semantic red token.
- Preserve stable geometry during async work.

## Layout contract
Desktop uses a command-first working canvas with runtime evidence adjacent to the mission surface. Secondary inspectors may open as drawers/modals without changing the truth ownership of the main surface.

Mobile collapses to a tabbed working mode rather than shrinking a desktop dashboard. Each tab owns its scroll context. No global overflow lock should be introduced merely to fit a table or panel.

## Interaction contract
- Native buttons for actions and anchors for navigation.
- Visible keyboard focus on every interactive control.
- Busy controls preserve their dimensions and expose aria-busy.
- Destructive/irreversible actions use app-owned confirmation.
- Loading, empty, unavailable and failure states explain the next safe action.
- Runtime success is never inferred from visual green alone.
- Paid/free model routing is shown from the verified route catalog, never from hardcoded availability.

## Motion
Motion is sparse and purposeful:
- short entry transition for newly materialized runtime evidence;
- subtle pulse for active readback only;
- no continuous decorative animation in idle state;
- honor prefers-reduced-motion.

## Responsive behavior
Target WCAG 2.2 AA. Maintain usable 320px+ layouts, 200% zoom compatibility, visible focus, semantic lists/tables, and touch targets that remain comfortably operable.

## Ownership and drift
DESIGN.md is durable visual intent. Runtime tokens live in src/features/control-surface-vnext/theme/biomodular.css; global accessibility/layout tokens live in src/index.css. New screens should reuse these sources instead of introducing screen-local colors or geometry constants.

## Verification
Visual changes require:
1. type-check and relevant component tests;
2. frontend smoke/endpoint gates;
3. production build;
4. real browser verification when available;
5. comparison with an existing sibling surface;
6. evidence/readback checks before any claim of live correctness.
