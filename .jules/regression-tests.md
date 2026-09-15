## 2026-08-25 - Regression Check Agent Zero, Swarm, FreeLLM API

**Learning:** When requested to verify and secure boundaries (Agent Zero, FreeLLM API, Swarm logic, Endpoints) using regression and runtime tests, mock testing against application logic in the frontend guarantees the explicit contracts aren't violated (e.g. `sovereignSwarmRegressionGuard.test.ts`), and running comprehensive E2E tests validates the bounds and mock configurations. The backend already validates FreeLLM bounds and direct OpenRouter transports.
**Action:** Always test actual business functions and component configurations rather than network status codes directly when running against a local or mock environment.
