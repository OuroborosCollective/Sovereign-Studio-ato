import test from "node:test";
import assert from "node:assert/strict";
import { inventoryFingerprint, validateLoopbackTarget } from "../src/inventory.mjs";

test("accepts only exact loopback MCP endpoint with explicit TCP port", () => {
  assert.equal(validateLoopbackTarget("http://127.0.0.1:10080/mcp"), "http://127.0.0.1:10080/mcp");
  for (const bad of [
    "https://example.com/mcp",
    "http://localhost:10080/mcp",
    "http://127.0.0.1/mcp",
    "http://127.0.0.1:10080/mcp?x=1",
    "http://127.0.0.1:10080/mcp#fragment",
    "http://127.0.0.1:10080/admin",
    "http://169.254.169.254:10080/mcp",
    "file:///etc/passwd",
    "",
  ]) assert.throws(() => validateLoopbackTarget(bad));
});

test("hashes schemas deterministically independent of key and tool ordering", () => {
  const a = [{ name: "beta", inputSchema: { type: "object", properties: { z: {type:"integer"}, a: {type:"string"} } } },
             { name: "alpha", inputSchema: { type: "object", properties: {} } }];
  const b = [{ name: "alpha", inputSchema: { properties: {}, type: "object" } },
             { name: "beta", inputSchema: { properties: { a: { type: "string" }, z: { type: "integer" } }, type: "object" } }];
  const x = inventoryFingerprint(a);
  const y = inventoryFingerprint(b);
  assert.equal(x.schemaVersion, "mcp-use.readonly-inventory.v1");
  assert.equal(x.count, 2);
  assert.equal(x.sha256, y.sha256);
  assert.match(x.sha256, /^[a-f0-9]{64}$/);
  assert.notEqual(x.sha256, inventoryFingerprint([{ name: "alpha", inputSchema: { type: "array" } }]).sha256);
});

test("fails closed on malformed tool catalog or unsafe metadata", () => {
  for (const bad of [null, {}, [{name:"a"}, {name:"a"}], [{name:"", inputSchema:{}}], [{name:"a", inputSchema:()=>{}}], Array.from({length:501}, (_,i)=>({name:"tool_"+i}))]) {
    assert.throws(() => inventoryFingerprint(bad));
  }
});

test("never elevates tool annotations to runtime authority", () => {
  const x = inventoryFingerprint([{name:"write_file", annotations:{readOnlyHint:true}, inputSchema:{type:"object"}}]);
  assert.equal(x.authority, "METADATA_ONLY");
  assert.equal(Object.hasOwn(x, "runtimeVerified"), false);
});
