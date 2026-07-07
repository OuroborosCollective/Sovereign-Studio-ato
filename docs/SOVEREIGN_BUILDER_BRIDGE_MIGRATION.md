# Builder Executor Bridge Migration

BuilderContainer must use `decideSovereignExecutorBridgeRoute` for code execution handoff decisions.

Required behavior:

- existing allowed executor decisions stay unchanged;
- missing repo or missing validated write access must stay blocked;
- when OpenHands and external workspace are absent but repo plus write access are ready, the route may fall back to `sovereign_internal_operator`;
- the UI may display the selected route, but the decision belongs to runtime.

This preserves the product truth: OpenHands is optional. Sovereign owns its internal operator path.
