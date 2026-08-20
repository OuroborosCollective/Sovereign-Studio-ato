import { execFileSync } from "node:child_process";
import { rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const stock = path.join(root, "node_modules", ".bin", "tsc");
const output = path.join(root, ".stock-tsc-output");
await rm(output, { recursive: true, force: true });
try {
  execFileSync(stock, ["-p", "tsconfig.json", "--outDir", output, "--declaration", "false"], { cwd: root, stdio: "pipe" });
  await import(path.join(output, "projections.js"));
  throw new Error("stock tsc unexpectedly produced callable Typia validators");
} catch (error) {
  const message = String(error?.message ?? error);
  if (message.includes("unexpectedly produced")) throw error;
  if (!message.includes("no transform has been configured")) {
    throw new Error("stock tsc did not fail with the expected missing-transformer proof");
  }
  console.log(JSON.stringify({ status: "STOCK_TSC_REJECTED_AS_EXPECTED" }));
} finally {
  await rm(output, { recursive: true, force: true });
}
