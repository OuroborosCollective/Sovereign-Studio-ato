const ALLOWED_EDGE_KINDS = new Set([
  "activates",
  "inhibits",
  "modulates",
  "projects-to",
  "relays-to",
  "compares-with",
  "authorizes",
  "records",
]);

export function validateNeuroGraph(graph) {
  if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
    return { ok: false, errors: ["INVALID_GRAPH_SHAPE"] };
  }
  const errors = [];
  const ids = new Set();
  for (const node of graph.nodes) {
    if (!node || typeof node.id !== "string" || !node.id) {
      errors.push("INVALID_NODE_ID");
      continue;
    }
    if (ids.has(node.id)) errors.push(`DUPLICATE_NODE:${node.id}`);
    ids.add(node.id);
  }
  for (const edge of graph.edges) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) {
      errors.push(`DANGLING_EDGE:${edge.from}->${edge.to}`);
    }
    if (!ALLOWED_EDGE_KINDS.has(edge.kind)) {
      errors.push(`INVALID_EDGE_KIND:${edge.kind}`);
    }
    if (!Number.isInteger(edge.delayBudgetMicros) || edge.delayBudgetMicros < 0) {
      errors.push(`INVALID_DELAY:${edge.from}->${edge.to}`);
    }
  }
  return { ok: errors.length === 0, errors };
}

export function adjacency(graph) {
  const result = new Map(graph.nodes.map((node) => [node.id, []]));
  for (const edge of graph.edges) result.get(edge.from)?.push(edge.to);
  for (const targets of result.values()) targets.sort();
  return result;
}

export function reachableNodes(graph, source) {
  const links = adjacency(graph);
  if (!links.has(source)) return [];
  const seen = new Set([source]);
  const queue = [source];
  while (queue.length > 0) {
    const current = queue.shift();
    for (const target of links.get(current) ?? []) {
      if (!seen.has(target)) {
        seen.add(target);
        queue.push(target);
      }
    }
  }
  return [...seen].sort();
}

export function degreeCentrality(graph) {
  const incoming = new Map(graph.nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(graph.nodes.map((node) => [node.id, 0]));
  for (const edge of graph.edges) {
    outgoing.set(edge.from, (outgoing.get(edge.from) ?? 0) + 1);
    incoming.set(edge.to, (incoming.get(edge.to) ?? 0) + 1);
  }
  return graph.nodes
    .map((node) => ({
      id: node.id,
      incoming: incoming.get(node.id) ?? 0,
      outgoing: outgoing.get(node.id) ?? 0,
      total: (incoming.get(node.id) ?? 0) + (outgoing.get(node.id) ?? 0),
    }))
    .sort((a, b) => b.total - a.total || a.id.localeCompare(b.id));
}

export function singlePointFailureCandidates(graph) {
  const allNodeIds = graph.nodes.map((node) => node.id).sort();
  const roots = graph.nodes.filter((node) => node.role === "input").map((node) => node.id);
  const sinks = new Set(graph.nodes.filter((node) => node.role === "effect").map((node) => node.id));
  const candidates = [];
  for (const removed of allNodeIds) {
    const reduced = {
      nodes: graph.nodes.filter((node) => node.id !== removed),
      edges: graph.edges.filter((edge) => edge.from !== removed && edge.to !== removed),
    };
    const remainingRoots = roots.filter((root) => root !== removed);
    const reachable = new Set(remainingRoots.flatMap((root) => reachableNodes(reduced, root)));
    const disconnectedSinks = [...sinks].filter((sink) => sink !== removed && !reachable.has(sink));
    if (disconnectedSinks.length > 0) candidates.push({ node: removed, disconnectedSinks });
  }
  return candidates;
}
