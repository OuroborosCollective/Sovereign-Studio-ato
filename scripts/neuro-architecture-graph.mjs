const VALID_ROLES = new Set([
  "input",
  "router",
  "verification",
  "side-channel",
  "effect",
  "evidence",
]);

const VALID_EDGE_KINDS = new Set([
  "relays-to",
  "authorizes",
  "records",
]);

export class NeuroGraphValidationError extends TypeError {
  /**
   * @param {string[]} errors
   */
  constructor(errors) {
    const normalizedErrors = [...errors].sort(compareStrings);
    super(`Invalid neuro-architecture graph: ${normalizedErrors.join(", ")}`);
    this.name = "NeuroGraphValidationError";
    this.code = "ERR_INVALID_NEURO_GRAPH";
    this.errors = normalizedErrors;
  }
}

/**
 * Validate the bounded directed neuro-architecture graph contract.
 *
 * Validation is pure, deterministic, and fail-closed. Error codes are sorted
 * lexicographically so equivalent malformed graphs produce identical output
 * regardless of node or edge insertion order.
 *
 * @param {unknown} graph
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function validateNeuroGraph(graph) {
  if (!isRecord(graph)) {
    return { ok: false, errors: ["INVALID_GRAPH"] };
  }

  const errors = [];
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];

  if (!Array.isArray(graph.nodes)) {
    errors.push("INVALID_NODES");
  }

  if (!Array.isArray(graph.edges)) {
    errors.push("INVALID_EDGES");
  }

  const nodeIds = new Set();

  for (let index = 0; index < nodes.length; index += 1) {
    const node = nodes[index];

    if (!isRecord(node) || !isNonEmptyString(node.id)) {
      errors.push(`INVALID_NODE:${index}`);
      continue;
    }

    const nodeId = node.id;

    if (nodeIds.has(nodeId)) {
      errors.push(`DUPLICATE_NODE:${nodeId}`);
    } else {
      nodeIds.add(nodeId);
    }

    if (!VALID_ROLES.has(node.role)) {
      errors.push(`INVALID_ROLE:${nodeId}`);
    }
  }

  const edgeKeys = new Set();

  for (let index = 0; index < edges.length; index += 1) {
    const edge = edges[index];

    if (
      !isRecord(edge) ||
      !isNonEmptyString(edge.from) ||
      !isNonEmptyString(edge.to)
    ) {
      errors.push(`INVALID_EDGE:${index}`);
      continue;
    }

    const edgeId = `${edge.from}->${edge.to}`;

    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) {
      errors.push(`DANGLING_EDGE:${edgeId}`);
    }

    if (!VALID_EDGE_KINDS.has(edge.kind)) {
      errors.push(`INVALID_EDGE_KIND:${edgeId}`);
    }

    if (
      !Number.isSafeInteger(edge.delayBudgetMicros) ||
      edge.delayBudgetMicros < 0
    ) {
      errors.push(`INVALID_DELAY:${edgeId}`);
    }

    const edgeKey = `${edge.from}\u0000${edge.to}\u0000${String(edge.kind)}`;

    if (edgeKeys.has(edgeKey)) {
      errors.push(`DUPLICATE_EDGE:${edgeId}:${String(edge.kind)}`);
    } else {
      edgeKeys.add(edgeKey);
    }
  }

  const normalizedErrors = [...new Set(errors)].sort(compareStrings);

  return {
    ok: normalizedErrors.length === 0,
    errors: normalizedErrors,
  };
}

/**
 * Return every node reachable from startId, including startId itself.
 *
 * @param {unknown} graph
 * @param {string} startId
 * @returns {string[]}
 */
export function reachableNodes(graph, startId) {
  assertValidGraph(graph);

  if (!isNonEmptyString(startId)) {
    return [];
  }

  const nodeIds = new Set(graph.nodes.map((node) => node.id));

  if (!nodeIds.has(startId)) {
    return [];
  }

  return [...reachableFromSources(graph, [startId])].sort(compareStrings);
}

/**
 * Calculate deterministic directed degree centrality.
 *
 * Ranking order:
 * 1. total degree descending
 * 2. out-degree descending
 * 3. in-degree descending
 * 4. node id ascending
 *
 * @param {unknown} graph
 * @returns {Array<{
 *   id: string,
 *   inDegree: number,
 *   outDegree: number,
 *   total: number
 * }>} 
 */
export function degreeCentrality(graph) {
  assertValidGraph(graph);

  const byNode = new Map(
    graph.nodes.map((node) => [
      node.id,
      {
        id: node.id,
        inDegree: 0,
        outDegree: 0,
        total: 0,
      },
    ]),
  );

  for (const edge of graph.edges) {
    const source = byNode.get(edge.from);
    const target = byNode.get(edge.to);

    source.outDegree += 1;
    source.total += 1;

    target.inDegree += 1;
    target.total += 1;
  }

  return [...byNode.values()].sort(
    (left, right) =>
      right.total - left.total ||
      right.outDegree - left.outDegree ||
      right.inDegree - left.inDegree ||
      compareStrings(left.id, right.id),
  );
}

/**
 * Find non-effect nodes whose removal disconnects one or more effect sinks
 * that were reachable in the intact graph from every remaining input path.
 *
 * @param {unknown} graph
 * @returns {Array<{ node: string, disconnectedSinks: string[] }>}
 */
export function singlePointFailureCandidates(graph) {
  assertValidGraph(graph);

  const inputIds = graph.nodes
    .filter((node) => node.role === "input")
    .map((node) => node.id)
    .sort(compareStrings);

  const effectSinkIds = graph.nodes
    .filter((node) => node.role === "effect")
    .map((node) => node.id)
    .sort(compareStrings);

  if (inputIds.length === 0 || effectSinkIds.length === 0) {
    return [];
  }

  const baselineReachable = reachableFromSources(graph, inputIds);

  const baselineSinks = effectSinkIds.filter((sinkId) =>
    baselineReachable.has(sinkId),
  );

  if (baselineSinks.length === 0) {
    return [];
  }

  const candidates = [];

  const orderedNodes = [...graph.nodes].sort((left, right) =>
    compareStrings(left.id, right.id),
  );

  for (const node of orderedNodes) {
    if (node.role === "effect") {
      continue;
    }

    const remainingInputs = inputIds.filter(
      (inputId) => inputId !== node.id,
    );

    const reachableAfterRemoval = reachableFromSources(
      graph,
      remainingInputs,
      node.id,
    );

    const disconnectedSinks = baselineSinks.filter(
      (sinkId) => !reachableAfterRemoval.has(sinkId),
    );

    if (disconnectedSinks.length > 0) {
      candidates.push({
        node: node.id,
        disconnectedSinks,
      });
    }
  }

  return candidates;
}

/**
 * @param {unknown} graph
 * @returns {asserts graph is {
 *   nodes: Array<{ id: string, role: string }>,
 *   edges: Array<{
 *     from: string,
 *     to: string,
 *     kind: string,
 *     delayBudgetMicros: number
 *   }>
 * }}
 */
function assertValidGraph(graph) {
  const result = validateNeuroGraph(graph);

  if (!result.ok) {
    throw new NeuroGraphValidationError(result.errors);
  }
}

/**
 * @param {{
 *   nodes: Array<{ id: string }>,
 *   edges: Array<{ from: string, to: string }>
 * }} graph
 * @param {string[]} sourceIds
 * @param {string | null} [removedNodeId]
 * @returns {Set<string>}
 */
function reachableFromSources(graph, sourceIds, removedNodeId = null) {
  const adjacency = new Map();

  for (const node of graph.nodes) {
    if (node.id !== removedNodeId) {
      adjacency.set(node.id, []);
    }
  }

  for (const edge of graph.edges) {
    if (
      edge.from === removedNodeId ||
      edge.to === removedNodeId ||
      !adjacency.has(edge.from) ||
      !adjacency.has(edge.to)
    ) {
      continue;
    }

    adjacency.get(edge.from).push(edge.to);
  }

  for (const neighbors of adjacency.values()) {
    neighbors.sort(compareStrings);
  }

  const queue = sourceIds
    .filter((sourceId) => adjacency.has(sourceId))
    .sort(compareStrings);

  const visited = new Set();

  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const current = queue[cursor];

    if (visited.has(current)) {
      continue;
    }

    visited.add(current);

    for (const neighbor of adjacency.get(current)) {
      if (!visited.has(neighbor)) {
        queue.push(neighbor);
      }
    }
  }

  return visited;
}

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/**
 * @param {unknown} value
 * @returns {value is string}
 */
function isNonEmptyString(value) {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.trim() === value
  );
}

/**
 * @param {string} left
 * @param {string} right
 * @returns {number}
 */
function compareStrings(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}