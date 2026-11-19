import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("the read-only pilot never invokes an MCP tool or exposes a server", () => {
  const source = readFileSync(new URL("../src/probe.mjs", import.meta.url), "utf8");
  assert.match(source, /\.listTools\(\)/);
  assert.doesNotMatch(source, /\.callTool\s*\(/);
  assert.doesNotMatch(source, /\.connectAll\s*\(/);
  assert.doesNotMatch(source, /\.createServer\s*\(/);
  assert.doesNotMatch(source, /\.listen\s*\(/);
});

test("the pilot cannot claim product runtime verification", () => {
  const source = readFileSync(new URL("../src/probe.mjs", import.meta.url), "utf8");
  assert.match(source, /productRuntimeVerified:\s*false/);
});
