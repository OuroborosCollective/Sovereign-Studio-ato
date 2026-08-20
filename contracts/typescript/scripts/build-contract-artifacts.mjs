import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const canonical = (value) => {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
};
const revision = process.env.CONTRACT_SOURCE_REVISION ?? execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
if (!/^[0-9a-f]{40}$/.test(revision)) throw new Error("Contract build requires a SHA-40 source revision");
const packageJson = JSON.parse(await readFile(path.join(root, "package.json"), "utf8"));
const sourcePath = "src/contracts.ts";
const source = await readFile(path.join(root, sourcePath));
const { CONTRACT_SCHEMA_VERSION, CONTRACT_SET_ID } = await import(path.join(root, "dist", "contracts.js"));
const { contractSchemas, mcpInputSchema, mcpOutputSchema } = await import(path.join(root, "dist", "projections.js"));
const contractDocument = {
  contractSetId: CONTRACT_SET_ID,
  schemaVersion: CONTRACT_SCHEMA_VERSION,
  components: contractSchemas.components,
  schemas: contractSchemas.schemas,
  mcp: { inputSchema: mcpInputSchema, outputSchema: mcpOutputSchema },
};
const contractDocumentHash = sha256(canonical(contractDocument));
const manifest = {
  artifactFormat: "sovereign.typescript-contract-pilot.v1",
  sourcePath,
  sourceBlobSha256: sha256(source),
  repositoryRevision: revision,
  schemaVersion: CONTRACT_SCHEMA_VERSION,
  contractSetId: CONTRACT_SET_ID,
  toolchain: {
    typia: packageJson.devDependencies.typia,
    ttsc: packageJson.devDependencies.ttsc,
    typescript: packageJson.devDependencies.typescript,
    buildConfigSha256: sha256(await readFile(path.join(root, "tsconfig.json")),),
  },
  contractDocumentHash,
  mcpInputSchemaHash: sha256(canonical(mcpInputSchema)),
  mcpOutputSchemaHash: sha256(canonical(mcpOutputSchema)),
};
await mkdir(path.join(root, "artifacts"), { recursive: true });
await writeFile(path.join(root, "artifacts", "contracts.json"), `${canonical(contractDocument)}\n`);
await writeFile(path.join(root, "artifacts", "manifest.json"), `${canonical(manifest)}\n`);
console.log(JSON.stringify({ status: "CONTRACT_ARTIFACTS_BUILT", contractDocumentHash, sourceBlobSha256: manifest.sourceBlobSha256, repositoryRevision: revision }));
