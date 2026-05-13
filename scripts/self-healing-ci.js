import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const SENSITIVE_DIRS = ['core', 'auth', 'security', 'crypto'];

// Plan output structure
const plan = {
  drift_detected: [],
  impacted_packages: [],
  execution_order: [],
  applied_fixes: []
};

// 1. Detect drift and auto-repair workspace
try {
  console.log("Checking workspace consistency...");
  // Use pnpm store status or install --frozen-lockfile to check for drift
  execSync('pnpm install --frozen-lockfile --prefer-offline', { stdio: 'pipe' });
} catch (error) {
  plan.drift_detected.push('pnpm-lock.yaml is not up to date or dependencies are missing');
  console.log("Drift detected. Repairing workspace...");
  // Repair
  try {
    execSync('pnpm install --no-frozen-lockfile', { stdio: 'inherit' });
    plan.applied_fixes.push('pnpm install --no-frozen-lockfile');
  } catch (repairError) {
    console.error("Failed to repair workspace:", repairError.message);
    process.exit(1);
  }
}

// 2. Parse monorepo structure and dependency graph
let workspaces = [];
try {
  const lsOutput = execSync('pnpm ls -r --depth -1 --json', { encoding: 'utf-8' });
  workspaces = JSON.parse(lsOutput);
} catch (e) {
  console.error("Failed to parse pnpm workspace:", e.message);
  process.exit(1);
}

// Ensure upstream builds before downstream (basic topological sort based on paths for this simple repo)
// For root and launch-bot-v1, launch-bot-v1 depends on nothing, root depends on nothing (independent)
// We'll just build them all based on path depth as a heuristic or alphabetical.
plan.execution_order = workspaces.map(w => w.name).sort();

// 3. Impact Analysis (Git diff)
let diffFiles = [];
try {
  // If in a PR, use origin/main as base. In this script we'll just diff against HEAD~1 or origin/main
  const diffOutput = execSync('git diff origin/main --name-only', { encoding: 'utf-8' });
  diffFiles = diffOutput.split('\n').filter(Boolean);
} catch (e) {
  // Fallback
  try {
    const diffOutput = execSync('git diff HEAD~1 --name-only', { encoding: 'utf-8' });
    diffFiles = diffOutput.split('\n').filter(Boolean);
  } catch(e2) {
    // No diff, maybe just pushed
    diffFiles = [];
  }
}

// Check sensitive areas
const touchesSensitive = diffFiles.some(file => {
  return SENSITIVE_DIRS.some(dir => file.startsWith(dir + '/'));
});

if (touchesSensitive) {
  console.error("SAFETY GATE: Modification of sensitive areas detected. Auto-fix blocked.");
  process.exit(1);
}

// Determine impacted packages
const impacted = new Set();
diffFiles.forEach(file => {
  let matched = false;
  for (const pkg of workspaces) {
    // If it's not root and file starts with package path
    const relPath = path.relative(process.cwd(), pkg.path);
    if (relPath && file.startsWith(relPath + '/')) {
      impacted.add(pkg.name);
      matched = true;
    }
  }
  // If not matched to a subpackage, it's the root package
  if (!matched && workspaces.find(w => w.path === process.cwd())) {
    impacted.add(workspaces.find(w => w.path === process.cwd()).name);
  }
});

plan.impacted_packages = Array.from(impacted);
if (plan.impacted_packages.length === 0) {
  // If no specific package impacted or cannot determine, assume all
  plan.impacted_packages = plan.execution_order;
}

// 4. Selective Execution
console.log(JSON.stringify(plan, null, 2));

const packagesToRun = plan.execution_order.filter(pkg => plan.impacted_packages.includes(pkg));

for (const pkgName of packagesToRun) {
  const pkg = workspaces.find(w => w.name === pkgName);
  console.log(`\nBuilding impacted package: ${pkgName}`);
  try {
    execSync('pnpm run build', { cwd: pkg.path, stdio: 'inherit' });
  } catch (e) {
    console.error(`Build failed for ${pkgName}. Attempting minimal repair not implemented yet.`);
    process.exit(1);
  }

  // Run tests if exist
  try {
    const pkgJson = JSON.parse(fs.readFileSync(path.join(pkg.path, 'package.json'), 'utf-8'));
    if (pkgJson.scripts && pkgJson.scripts.test) {
      console.log(`\nTesting impacted package: ${pkgName}`);
      execSync('pnpm run test:run', { cwd: pkg.path, stdio: 'inherit' });
    }
  } catch (e) {
    console.error(`Tests failed for ${pkgName}.`);
    // Tests failed: do NOT auto-merge (we'll just exit with 1 to fail CI)
    process.exit(1);
  }
}

console.log("\nCI Health State: GREEN. All impacted packages built and tested successfully.");
