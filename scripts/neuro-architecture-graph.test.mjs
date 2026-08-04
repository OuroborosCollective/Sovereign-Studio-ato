import assert from "node:assert/strict";
import test from "node:test";
import {
  degreeCentrality,
  reachableNodes,
  singlePointFailureCandidates,
  validateNeuroGraph,
} from "./neuro-architecture-graph.mjs";

const graph = {
  nodes: [
    { id: "sensory-intake", role: "input" },
    { id: "thalamic-routing", role: "router" },
    { id: "deterministic-verification", role: "verification" },
    { id: "cognitive-side-channel", role: "side-channel" },
    { id: "motor-authorization", role: "effect" },
    { id: "evidence", role: "evidence" },
  ],
  edges: [
    {
      from: "sensory-intake",
      to: "thalamic-routing",
      kind: "relays-to",
      delayBudgetMicros: 5000,
    },
    {
      from: "thalamic-routing",
      to: "deterministic-verification",
      kind: "relays-to",
      delayBudgetMicros: 5000,
    },
    {
      from: "thalamic-routing",
      to: "cognitive-side-channel",
      kind: "relays-to",
      delayBudgetMicros: 25000,
    },
    {
      from: "deterministic-verification",
      to: "motor-authorization",
      kind: "authorizes",
      delayBudgetMicros: 10000,
    },
    {
      from: "deterministic-verification",
      to: "evidence",
      kind: "records",
      delayBudgetMicros: 10000,
    },
    {
      from: "cognitive-side-channel",
      to: "evidence",
      kind: "records",
      delayBudgetMicros: 50000,
    },
  ],
};

test("validates the bounded directed graph contract", () => {
  assert.deepEqual(validateNeuroGraph(graph), { ok: true, errors: [] });
});

test("finds deterministic reachability without depending on insertion order", () => {
  assert.deepEqual(reachableNodes(graph, "sensory-intake"), [
    "cognitive-side-channel",
    "deterministic-verification",
    "evidence",
    "motor-authorization",
    "sensory-intake",
    "thalamic-routing",
  ]);
});

test("ranks the routing and verification surfaces by graph degree", () => {
  const centrality = degreeCentrality(graph);
  assert.equal(centrality[0].id, "deterministic-verification");
  assert.equal(centrality[0].total, 3);
  assert.equal(centrality[1].id, "thalamic-routing");
  assert.equal(centrality[1].total, 3);
});

test("reports single-point failure candidates for the effect path", () => {
  const candidates = singlePointFailureCandidates(graph);
  assert.deepEqual(candidates, [
    { node: "deterministic-verification", disconnectedSinks: ["motor-authorization"] },
    { node: "sensory-intake", disconnectedSinks: ["motor-authorization"] },
    { node: "thalamic-routing", disconnectedSinks: ["motor-authorization"] },
  ]);
});

test("fails closed on dangling edges and invalid delay budgets", () => {
  const invalid = {
    nodes: graph.nodes,
    edges: [
      {
        from: "sensory-intake",
        to: "unknown-node",
        kind: "relays-to",
        delayBudgetMicros: -1,
      },
    ],
  };

  assert.deepEqual(validateNeuroGraph(invalid), {
    ok: false,
    errors: [
      "DANGLING_EDGE:sensory-intake->unknown-node",
      "INVALID_DELAY:sensory-intake->unknown-node",
    ],
  });
});
