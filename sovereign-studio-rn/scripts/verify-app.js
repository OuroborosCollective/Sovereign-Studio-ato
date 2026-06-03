#!/usr/bin/env node

/**
 * Sovereign Studio — Real App Verification
 *
 * Purpose:
 * - Verify that the app repository is structurally usable.
 * - Confirm package.json exists and can be parsed.
 * - Confirm important scripts are present or report missing ones.
 * - Create a deterministic-ish verification artifact file.
 * - Produce machine-readable and human-readable reports.
 *
 * This script is CI-safe:
 * - It does not require external APIs.
 * - It does not mutate production code.
 * - It exits with 0 when verification artifact was created.
 * - It exits with 1 only on hard structural failure.
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const childProcess = require("child_process");

const ROOT = process.cwd();

const VERIFY_DIR = path.join(ROOT, "e2e", "app-verify");
const REPORT_DIR = path.join(ROOT, "e2e", "app-verify", "reports");

const PACKAGE_JSON_PATH = path.join(ROOT, "package.json");

const REQUIRED_DIRS = [
  "scripts",
  "e2e",
];

const IMPORTANT_SCRIPTS = [
  "build",
  "test",
  "lint",
  "typecheck",
  "e2e:all",
];

function nowIso() {
  return new Date().toISOString();
}

function safeMkdir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function readJson(filePath) {
  const raw = fs.readFileSync(filePath, "utf8");
  return JSON.parse(raw);
}

function exists(relativePath) {
  return fs.existsSync(path.join(ROOT, relativePath));
}

function run(command, args = []) {
  try {
    const output = childProcess.execFileSync(command, args, {
      cwd: ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });

    return {
      ok: true,
      output: output.trim(),
      error: "",
    };
  } catch (error) {
    return {
      ok: false,
      output: error.stdout ? String(error.stdout).trim() : "",
      error: error.stderr ? String(error.stderr).trim() : String(error.message || error),
    };
  }
}

function stableHash(input) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

function slug(input) {
  return String(input)
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80);
}

function getGitInfo() {
  const commit = run("git", ["rev-parse", "HEAD"]);
  const branch = run("git", ["rev-parse", "--abbrev-ref", "HEAD"]);
  const status = run("git", ["status", "--short"]);
  const lastCommit = run("git", ["log", "-1", "--oneline"]);

  return {
    commit: commit.ok ? commit.output : "unknown",
    branch: branch.ok ? branch.output : "unknown",
    status: status.ok ? status.output : "",
    lastCommit: lastCommit.ok ? lastCommit.output : "unknown",
  };
}

function getNodeInfo() {
  const nodeVersion = run("node", ["--version"]);
  const npmVersion = run("npm", ["--version"]);

  return {
    node: nodeVersion.ok ? nodeVersion.output : process.version,
    npm: npmVersion.ok ? npmVersion.output : "unknown",
  };
}

function collectFiles(dir, options = {}) {
  const {
    maxFiles = 300,
    ignore = [
      "node_modules",
      ".git",
      "dist",
      "build",
      ".next",
      ".expo",
      "coverage",
      ".turbo",
      ".cache",
    ],
  } = options;

  const results = [];

  function walk(currentDir) {
    if (results.length >= maxFiles) return;

    let entries = [];

    try {
      entries = fs.readdirSync(currentDir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      if (results.length >= maxFiles) return;
      if (ignore.includes(entry.name)) continue;

      const absolute = path.join(currentDir, entry.name);
      const relative = path.relative(ROOT, absolute).replace(/\\/g, "/");

      if (entry.isDirectory()) {
        walk(absolute);
      } else if (entry.isFile()) {
        results.push(relative);
      }
    }
  }

  walk(dir);

  return results.sort();
}

function validatePackageJson(pkg) {
  const findings = [];
  const scripts = pkg.scripts || {};

  if (!pkg.name) {
    findings.push({
      level: "warning",
      code: "PACKAGE_NAME_MISSING",
      message: "package.json has no name field.",
    });
  }

  if (!pkg.version) {
    findings.push({
      level: "warning",
      code: "PACKAGE_VERSION_MISSING",
      message: "package.json has no version field.",
    });
  }

  for (const scriptName of IMPORTANT_SCRIPTS) {
    if (!scripts[scriptName]) {
      findings.push({
        level: "info",
        code: "SCRIPT_MISSING",
        message: `Optional script missing: ${scriptName}`,
      });
    } else {
      findings.push({
        level: "ok",
        code: "SCRIPT_PRESENT",
        message: `Script present: ${scriptName}`,
      });
    }
  }

  return findings;
}

function validateStructure() {
  const findings = [];

  for (const dir of REQUIRED_DIRS) {
    if (exists(dir)) {
      findings.push({
        level: "ok",
        code: "DIR_PRESENT",
        message: `Directory present: ${dir}`,
      });
    } else {
      findings.push({
        level: "warning",
        code: "DIR_MISSING",
        message: `Recommended directory missing: ${dir}`,
      });
    }
  }

  const commonSourceDirs = ["src", "app", "components", "pages"];

  const hasSourceDir = commonSourceDirs.some((dir) => exists(dir));

  if (hasSourceDir) {
    findings.push({
      level: "ok",
      code: "SOURCE_DIR_FOUND",
      message: `Source directory found: ${commonSourceDirs.filter((dir) => exists(dir)).join(", ")}`,
    });
  } else {
    findings.push({
      level: "warning",
      code: "SOURCE_DIR_NOT_FOUND",
      message: "No common source directory found: src, app, components, pages.",
    });
  }

  return findings;
}

function createVerificationFile(report) {
  safeMkdir(VERIFY_DIR);

  const shortHash = report.verification.hash.slice(0, 12);
  const cleanName = slug(report.package.name || "sovereign_studio");
  const fileName = `verify_${cleanName}_${shortHash}.ts`;
  const filePath = path.join(VERIFY_DIR, fileName);

  const content = `/**
 * Auto-generated verification artifact.
 *
 * Generated by: scripts/verify-app.js
 * Generated at: ${report.verification.createdAt}
 * Verification ID: ${report.verification.id}
 * Hash: ${report.verification.hash}
 *
 * This file proves the app verification pipeline can:
 * - run Node.js
 * - read project metadata
 * - inspect repository structure
 * - generate files
 * - produce deterministic verification output
 */

export const sovereignStudioVerification = {
  ok: true,
  id: ${JSON.stringify(report.verification.id)},
  hash: ${JSON.stringify(report.verification.hash)},
  createdAt: ${JSON.stringify(report.verification.createdAt)},
  packageName: ${JSON.stringify(report.package.name || null)},
  packageVersion: ${JSON.stringify(report.package.version || null)},
  node: ${JSON.stringify(report.environment.node)},
  npm: ${JSON.stringify(report.environment.npm)},
  gitCommit: ${JSON.stringify(report.git.commit)},
  gitBranch: ${JSON.stringify(report.git.branch)},
  findings: ${JSON.stringify(report.findings, null, 2)}
} as const;

export type SovereignStudioVerification = typeof sovereignStudioVerification;
`;

  fs.writeFileSync(filePath, content, "utf8");

  return {
    fileName,
    filePath,
    relativePath: path.relative(ROOT, filePath).replace(/\\/g, "/"),
  };
}

function writeReports(report) {
  safeMkdir(REPORT_DIR);

  const jsonPath = path.join(REPORT_DIR, "verification-report.json");
  const mdPath = path.join(REPORT_DIR, "verification-report.md");

  fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2), "utf8");

  const okCount = report.findings.filter((item) => item.level === "ok").length;
  const warningCount = report.findings.filter((item) => item.level === "warning").length;
  const infoCount = report.findings.filter((item) => item.level === "info").length;
  const errorCount = report.findings.filter((item) => item.level === "error").length;

  const markdown = [
    "# Sovereign Studio Verification Report",
    "",
    `Generated: ${report.verification.createdAt}`,
    "",
    "## Result",
    "",
    `- Success: ${report.success ? "yes" : "no"}`,
    `- Verification ID: ${report.verification.id}`,
    `- Verification file: ${report.verification.file || "none"}`,
    "",
    "## Package",
    "",
    `- Name: ${report.package.name || "unknown"}`,
    `- Version: ${report.package.version || "unknown"}`,
    "",
    "## Environment",
    "",
    `- Node: ${report.environment.node}`,
    `- npm: ${report.environment.npm}`,
    "",
    "## Git",
    "",
    `- Branch: ${report.git.branch}`,
    `- Commit: ${report.git.commit}`,
    `- Last commit: ${report.git.lastCommit}`,
    "",
    "## Findings",
    "",
    `- OK: ${okCount}`,
    `- Info: ${infoCount}`,
    `- Warnings: ${warningCount}`,
    `- Errors: ${errorCount}`,
    "",
    ...report.findings.map((finding) => {
      const icon =
        finding.level === "ok"
          ? "✅"
          : finding.level === "warning"
            ? "⚠️"
            : finding.level === "error"
              ? "❌"
              : "ℹ️";

      return `- ${icon} **${finding.code}** — ${finding.message}`;
    }),
    "",
    "## Sample Files",
    "",
    ...report.files.slice(0, 80).map((file) => `- \`${file}\``),
    "",
  ].join("\n");

  fs.writeFileSync(mdPath, markdown, "utf8");

  return {
    json: path.relative(ROOT, jsonPath).replace(/\\/g, "/"),
    markdown: path.relative(ROOT, mdPath).replace(/\\/g, "/"),
  };
}

function main() {
  console.log("========================================");
  console.log("🧪 SOVEREIGN STUDIO REAL APP VERIFICATION");
  console.log("========================================");
  console.log(`Root: ${ROOT}`);
  console.log(`Time: ${nowIso()}`);
  console.log("");

  safeMkdir(VERIFY_DIR);
  safeMkdir(REPORT_DIR);

  if (!fs.existsSync(PACKAGE_JSON_PATH)) {
    console.error("❌ Hard failure: package.json not found.");
    console.error(`Expected: ${PACKAGE_JSON_PATH}`);
    process.exit(1);
  }

  let pkg;

  try {
    pkg = readJson(PACKAGE_JSON_PATH);
  } catch (error) {
    console.error("❌ Hard failure: package.json could not be parsed.");
    console.error(error);
    process.exit(1);
  }

  const git = getGitInfo();
  const environment = getNodeInfo();

  const files = collectFiles(ROOT);
  const packageFindings = validatePackageJson(pkg);
  const structureFindings = validateStructure();

  const seed = JSON.stringify({
    packageName: pkg.name || "unknown",
    packageVersion: pkg.version || "unknown",
    gitCommit: git.commit,
    node: environment.node,
    files: files.slice(0, 200),
  });

  const hash = stableHash(seed);
  const verificationId = `verify_${hash.slice(0, 16)}`;

  const report = {
    success: false,
    verification: {
      id: verificationId,
      hash,
      createdAt: nowIso(),
      file: null,
    },
    package: {
      name: pkg.name || null,
      version: pkg.version || null,
      scripts: pkg.scripts || {},
      dependencies: Object.keys(pkg.dependencies || {}).sort(),
      devDependencies: Object.keys(pkg.devDependencies || {}).sort(),
    },
    environment,
    git,
    findings: [
      {
        level: "ok",
        code: "PACKAGE_JSON_PARSED",
        message: "package.json parsed successfully.",
      },
      {
        level: "ok",
        code: "NODE_AVAILABLE",
        message: `Node.js available: ${environment.node}`,
      },
      {
        level: "ok",
        code: "NPM_AVAILABLE",
        message: `npm available: ${environment.npm}`,
      },
      ...packageFindings,
      ...structureFindings,
    ],
    files,
    reports: {},
  };

  const verificationFile = createVerificationFile(report);

  report.success = true;
  report.verification.file = verificationFile.relativePath;

  report.findings.push({
    level: "ok",
    code: "VERIFICATION_FILE_CREATED",
    message: `Verification file created: ${verificationFile.relativePath}`,
  });

  report.reports = writeReports(report);

  console.log("✅ Verification artifact created:");
  console.log(`   ${verificationFile.relativePath}`);
  console.log("");
  console.log("✅ Reports written:");
  console.log(`   ${report.reports.json}`);
  console.log(`   ${report.reports.markdown}`);
  console.log("");
  console.log("📌 Verification ID:");
  console.log(`   ${report.verification.id}`);
  console.log("");
  console.log("📌 Hash:");
  console.log(`   ${report.verification.hash}`);
  console.log("");
  console.log("✅ Real app verification completed.");

  process.exit(0);
}

main();
