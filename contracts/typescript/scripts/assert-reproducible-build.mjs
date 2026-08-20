import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const hash = async (file) => createHash("sha256").update(await readFile(file)).digest("hex");
const build = () => execFileSync("pnpm", ["build"], { cwd: root, stdio: "pipe" });
const artifact = (name) => path.join(root, "artifacts", name);

build();
const first = { contracts: await hash(artifact("contracts.json")), manifest: await hash(artifact("manifest.json")) };
await rm(path.join(root, "dist"), { recursive: true, force: true });
await rm(path.join(root, "artifacts"), { recursive: true, force: true });
build();
const second = { contracts: await hash(artifact("contracts.json")), manifest: await hash(artifact("manifest.json")) };
if (first.contracts !== second.contracts || first.manifest !== second.manifest) throw new Error("contract artifacts are not reproducible");
console.log(JSON.stringify({ status: "REPRODUCIBLE_CONTRACT_ARTIFACTS", artifacts: second }));
