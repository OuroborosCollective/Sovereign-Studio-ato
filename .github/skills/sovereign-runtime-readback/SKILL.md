---
name: sovereign-runtime-readback
description: Verify Sovereign runtime effects by correlating exact revision, immutable artifact, deployment, Docker, PatchMon, database/provider state and functional target-system readback.
---

# Sovereign Runtime Readback

Use this skill whenever a mission makes or evaluates a runtime, deployment, container, database, provider or other external-system claim.

Seek the strongest applicable causal chain:

`exact repository/merge revision -> immutable artifact or image digest -> deployment receipt -> running target identity -> Docker/container state -> PatchMon/Fleet observation -> application functional readback -> persistence/provider readback`.

Rules:

- repository implementation and CI do not prove deployment;
- deployment observation does not prove correct runtime behavior;
- liveness and health indicators are sensors, not complete success evidence;
- PatchMon is an evidence lane, not a code verdict engine;
- database changes require real migration/schema/constraint/index readback where applicable;
- provider configuration requires fresh provider/route readiness evidence before runtime claims;
- for ambiguous writes/timeouts, read the target state before retrying;
- do not manufacture runtime results when tools or target access are unavailable.

Return the strongest scoped truth class supported by evidence. If live evidence is unavailable, keep runtime explicitly `UNVERIFIED`/`BLOCKED` even when repository and CI evidence are green.