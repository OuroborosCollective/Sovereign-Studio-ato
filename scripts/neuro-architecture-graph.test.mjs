import assert from "node:assert/strict";
import test from "node:test";

import {
  NeuroGraphValidationError,
  degreeCentrality,
  reachableNodes,
  singlePointFailureCandidates,
  validateNeuroGraph,
} from "./neuro-architecture-graph.mjs";

const graph = deepFreeze({
  nodes: [
    { id: "sensory-intake", role: "input" },
    { id: "thalamic-routing", role: "router" },
    {
      id: "deterministic-verification",
      role: "verification",
    },
    {
      id: "cognitive-side-channel",
      role: "side-channel",
    },
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
});

test("validates the bounded directed graph contract", () => {
  assert.deepEqual(validateNeuroGraph(graph), {
    ok: true,
    errors: [],
  });
});

test(
  "finds deterministic reachability without depending on insertion order",
  () => {
    const expected = [
      "cognitive-side-channel",
      "deterministic-verification",
      "evidence",
      "motor-authorization",
      "sensory-intake",
      "thalamic-routing",
    ];

    assert.deepEqual(
      reachableNodes(graph, "sensory-intake"),
      expected,
    );

    assert.deepEqual(
      reachableNodes(
        reverseGraphInsertionOrder(graph),
        "sensory-intake",
      ),
      expected,
    );

    assert.deepEqual(
      reachableNodes(graph, "unknown-node"),
      [],
    );
  },
);

test(
  "ranks graph degree deterministically with explicit tie breakers",
  () => {
    const expected = [
      {
        id: "deterministic-verification",
        inDegree: 1,
        outDegree: 2,
        total: 3,
      },
      {
        id: "thalamic-routing",
        inDegree: 1,
        outDegree: 2,
        total: 3,
      },
      {
        id: "cognitive-side-channel",
        inDegree: 1,
        outDegree: 1,
        total: 2,
      },
      {
        id: "evidence",
        inDegree: 2,
        outDegree: 0,
        total: 2,
      },
      {
        id: "sensory-intake",
        inDegree: 0,
        outDegree: 1,
        total: 1,
      },
      {
        id: "motor-authorization",
        inDegree: 1,
        outDegree: 0,
        total: 1,
      },
    ];

    assert.deepEqual(
      degreeCentrality(graph),
      expected,
    );

    assert.deepEqual(
      degreeCentrality(reverseGraphInsertionOrder(graph)),
      expected,
    );
  },
);

test(
  "reports single-point failure candidates for the effect path",
  () => {
    const expected = [
      {
        node: "deterministic-verification",
        disconnectedSinks: ["motor-authorization"],
      },
      {
        node: "sensory-intake",
        disconnectedSinks: ["motor-authorization"],
      },
      {
        node: "thalamic-routing",
        disconnectedSinks: ["motor-authorization"],
      },
    ];

    assert.deepEqual(
      singlePointFailureCandidates(graph),
      expected,
    );

    assert.deepEqual(
      singlePointFailureCandidates(
        reverseGraphInsertionOrder(graph),
      ),
      expected,
    );
  },
);

test(
  "does not report a node when an independent input path preserves the effect",
  () => {
    const redundantGraph = {
      nodes: [
        { id: "input-a", role: "input" },
        { id: "input-b", role: "input" },
        { id: "router-a", role: "router" },
        { id: "router-b", role: "router" },
        { id: "effect", role: "effect" },
      ],
      edges: [
        {
          from: "input-a",
          to: "router-a",
          kind: "relays-to",
          delayBudgetMicros: 1,
        },
        {
          from: "router-a",
          to: "effect",
          kind: "authorizes",
          delayBudgetMicros: 1,
        },
        {
          from: "input-b",
          to: "router-b",
          kind: "relays-to",
          delayBudgetMicros: 1,
        },
        {
          from: "router-b",
          to: "effect",
          kind: "authorizes",
          delayBudgetMicros: 1,
        },
      ],
    };

    assert.deepEqual(
      singlePointFailureCandidates(redundantGraph),
      [],
    );
  },
);

test(
  "fails closed on dangling edges and invalid delay budgets",
  () => {
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
  },
);

test(
  "rejects duplicate identities and duplicate directed edge contracts",
  () => {
    const invalid = {
      nodes: [
        { id: "a", role: "input" },
        { id: "a", role: "input" },
        { id: "b", role: "effect" },
      ],
      edges: [
        {
          from: "a",
          to: "b",
          kind: "authorizes",
          delayBudgetMicros: 0,
        },
        {
          from: "a",
          to: "b",
          kind: "authorizes",
          delayBudgetMicros: 0,
        },
      ],
    };

    assert.deepEqual(validateNeuroGraph(invalid), {
      ok: false,
      errors: [
        "DUPLICATE_EDGE:a->b:authorizes",
        "DUPLICATE_NODE:a",
      ],
    });
  },
);

test(
  "analytics reject malformed graphs with a stable typed error",
  () => {
    const invalid = {
      nodes: [
        {
          id: "input",
          role: "input",
        },
      ],
      edges: [
        {
          from: "input",
          to: "missing",
          kind: "relays-to",
          delayBudgetMicros: 1,
        },
      ],
    };

    const operations = [
      () => reachableNodes(invalid, "input"),
      () => degreeCentrality(invalid),
      () => singlePointFailureCandidates(invalid),
    ];

    for (const operation of operations) {
      assert.throws(operation, (error) => {
        assert.equal(
          error instanceof NeuroGraphValidationError,
          true,
        );

        assert.equal(
          error.name,
          "NeuroGraphValidationError",
        );

        assert.equal(
          error.code,
          "ERR_INVALID_NEURO_GRAPH",
        );

        assert.deepEqual(error.errors, [
          "DANGLING_EDGE:input->missing",
        ]);

        return true;
      });
    }
  },
);

test(
  "all graph operations remain pure and do not mutate caller data",
  () => {
    const mutableGraph = cloneGraph(graph);
    const before = JSON.stringify(mutableGraph);

    validateNeuroGraph(mutableGraph);
    reachableNodes(mutableGraph, "sensory-intake");
    degreeCentrality(mutableGraph);
    singlePointFailureCandidates(mutableGraph);

    assert.equal(
      JSON.stringify(mutableGraph),
      before,
    );
  },
);

function reverseGraphInsertionOrder(value) {
  return {
    nodes: [...value.nodes].reverse(),
    edges: [...value.edges].reverse(),
  };
}

function cloneGraph(value) {
  return JSON.parse(JSON.stringify(value));
}

function deepFreeze(value) {
  if (
    value !== null &&
    typeof value === "object" &&
    !Object.isFrozen(value)
  ) {
    Object.freeze(value);

    for (const nested of Object.values(value)) {
      deepFreeze(nested);
    }
  }

  return value;
}