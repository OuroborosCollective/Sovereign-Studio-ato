## 2025-05-28 - [Refactoring ProductMagicApp.tsx]
**Learning:** Large React components (200+ lines) with mixed state and UI benefit significantly from custom hooks and component decomposition.
**Action:** Always look for logical units of state and UI blocks to extract. Use custom hooks for complex state management and isolated components for logical UI sections.

## 2026-06-13 - [Incremental Canvas Sync]
**Learning:** In Fabric.js integrations, O(N) map rebuilds and canvas iterations during Redux-to-Canvas sync are major bottlenecks. Maintaining an incremental ID-to-object map enables O(1) lookups and significantly reduces sync overhead.
**Action:** Always maintain incremental maps for object synchronization. Update the map during creation and removal, and use it for existence checks instead of clearing/rebuilding or iterating over all canvas objects.
