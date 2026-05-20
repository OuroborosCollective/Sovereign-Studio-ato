import { execSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');

const SENSITIVE_DIRS = ['core/', 'auth/', 'security/', 'crypto/'];

function runCmd(cmd, opts = {}) {
    try {
        return execSync(cmd, { cwd: rootDir, encoding: 'utf-8', stdio: 'pipe', ...opts });
    } catch (e) {
        return null;
    }
}

function runCmdThrow(cmd, opts = {}) {
    return execSync(cmd, { cwd: rootDir, encoding: 'utf-8', stdio: 'inherit', ...opts });
}

function isSensitive(file) {
    return SENSITIVE_DIRS.some(dir => file.startsWith(dir) || file.includes(`/${dir}`));
}

function checkSafetyGates() {
    const baseRef = process.env.GITHUB_BASE_REF;
    const compareRef = baseRef ? `origin/${baseRef}...HEAD` : 'HEAD~1...HEAD';

    const gitDiff = runCmd(`git diff --name-only ${compareRef}`);
    if (!gitDiff) return [];

    const files = gitDiff.trim().split('\n').filter(Boolean);

    for (const file of files) {
        if (isSensitive(file)) {
            console.error(JSON.stringify({
                error: `Safety Gate Exception: Cannot auto-heal sensitive file ${file}`,
                detected_drift: [],
                impacted_packages: [],
                execution_order: [],
                applied_fixes: []
            }, null, 2));
            process.exit(1);
        }
    }

    return files;
}

function detectDrift() {
    const drift = [];

    const lsOutput = runCmd('pnpm ls -r --depth -1 --json');
    if (!lsOutput) {
        drift.push('workspace_resolution_error');
    } else {
        try {
            const pkgs = JSON.parse(lsOutput);
            if (!Array.isArray(pkgs) || pkgs.length === 0) {
                drift.push('empty_workspace');
            }
        } catch (e) {
            drift.push('invalid_workspace_json');
        }
    }

    // Checking for outdated lockfile
    try {
        // Test if lockfile matches package.json
        execSync('pnpm install --frozen-lockfile', { cwd: rootDir, encoding: 'utf-8', stdio: 'ignore' });
    } catch (e) {
        drift.push('outdated_lockfile');
    }

    return drift;
}

function getWorkspacePackages() {
    const output = runCmd('pnpm ls -r --depth -1 --json');
    if (!output) return [];
    try {
        const pkgs = JSON.parse(output);
        for (const pkg of pkgs) {
            const pkgJsonPath = path.join(pkg.path, 'package.json');
            if (fs.existsSync(pkgJsonPath)) {
                const pkgJson = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf8'));
                pkg.dependencies = pkgJson.dependencies || {};
                pkg.devDependencies = pkgJson.devDependencies || {};
            } else {
                pkg.dependencies = {};
                pkg.devDependencies = {};
            }
        }
        return pkgs;
    } catch {
        return [];
    }
}

function getImpactedPackages(files) {
    const impacted = new Set();
    const workspacePackages = getWorkspacePackages();

    for (const file of files) {
        let found = false;
        const sortedPkgs = [...workspacePackages].sort((a, b) => b.path.length - a.path.length);

        for (const pkg of sortedPkgs) {
            const relativePkgPath = path.relative(rootDir, pkg.path);
            if (relativePkgPath === '') continue;

            if (file.startsWith(`${relativePkgPath}/`) || file === relativePkgPath) {
                impacted.add(pkg.name);
                found = true;
                break;
            }
        }

        if (!found) {
            const rootPkg = workspacePackages.find(p => path.relative(rootDir, p.path) === '');
            if (rootPkg) {
                impacted.add(rootPkg.name);
            } else {
                impacted.add('.');
            }
        }
    }

    return Array.from(impacted);
}

function getExecutionOrder(impactedPackages) {
    if (impactedPackages.length === 0) return [];

    const pkgs = getWorkspacePackages();
    if (pkgs.length === 0) return impactedPackages;

    const nameToPkg = new Map(pkgs.map(p => [p.name, p]));
    const impactedAndDependents = new Set();
    const toProcess = new Set(impactedPackages);

    for (const pkgName of impactedPackages) {
        const pkg = nameToPkg.get(pkgName);
        if (pkg) {
            const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
            for (const depName of Object.keys(deps)) {
                if (nameToPkg.has(depName)) {
                    impactedAndDependents.add(depName);
                }
            }
        }
    }

    while (toProcess.size > 0) {
        const current = toProcess.values().next().value;
        toProcess.delete(current);
        impactedAndDependents.add(current);

        for (const pkg of pkgs) {
            const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
            if (Object.keys(deps).some(depName => depName === current)) {
                if (!impactedAndDependents.has(pkg.name)) {
                    toProcess.add(pkg.name);
                }
            }
        }
    }

    const depth = new Map();
    function getDepth(pkgName, visited = new Set()) {
        if (depth.has(pkgName)) return depth.get(pkgName);
        if (visited.has(pkgName)) return 0;

        visited.add(pkgName);
        let maxDepDepth = 0;
        const pkg = nameToPkg.get(pkgName);

        if (pkg) {
            const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
            for (const depName of Object.keys(deps)) {
                if (nameToPkg.has(depName)) {
                    maxDepDepth = Math.max(maxDepDepth, getDepth(depName, visited));
                }
            }
        }

        visited.delete(pkgName);
        const res = maxDepDepth + 1;
        depth.set(pkgName, res);
        return res;
    }

    const result = Array.from(impactedAndDependents);
    result.sort((a, b) => getDepth(a) - getDepth(b));

    return result;
}

function autoRepair(drift) {
    const fixes = [];

    if (drift.includes('workspace_resolution_error') ||
        drift.includes('empty_workspace') ||
        drift.includes('invalid_workspace_json') ||
        drift.includes('outdated_lockfile')) {

        runCmd('pnpm install');
        fixes.push('pnpm_install');
    }

    return fixes;
}

function runBuilds(executionOrder) {
    if (executionOrder.length === 0) return;

    for (const pkg of executionOrder) {
        try {
            runCmdThrow(`pnpm --filter ${pkg} run --if-present build`);
        } catch (e) {
            console.error(`Build failed for ${pkg}. Attempting minimal repair...`);
            try {
                runCmd('pnpm install');
                runCmdThrow(`pnpm --filter ${pkg} run --if-present build`);
            } catch (e2) {
                process.exit(1);
            }
        }
    }
}

function runTests(executionOrder) {
    if (executionOrder.length === 0) return;

    for (const pkg of executionOrder) {
        try {
            runCmdThrow(`pnpm --filter ${pkg} run --if-present test:run`);
            runCmdThrow(`pnpm --filter ${pkg} run --if-present test`);
        } catch (e) {
            try {
                runCmd('pnpm install');
                runCmdThrow(`pnpm --filter ${pkg} run --if-present test:run`);
                runCmdThrow(`pnpm --filter ${pkg} run --if-present test`);
            } catch (e2) {
                process.exit(1);
            }
        }
    }
}

function main() {
    if (process.argv.includes('--patch-only')) {
        const patch = runCmd('git diff');
        if (patch && patch.trim() !== '') {
            console.log(patch);
        }
        return;
    }

    const files = checkSafetyGates();

    const drift = detectDrift();
    const applied_fixes = autoRepair(drift);

    const impacted = getImpactedPackages(files);
    const execution_order = getExecutionOrder(impacted);

    const plan = {
        detected_drift: drift,
        impacted_packages: impacted,
        execution_order: execution_order,
        applied_fixes: applied_fixes
    };

    console.log(JSON.stringify(plan, null, 2));

    if (execution_order.length > 0) {
        runBuilds(execution_order);
        runTests(execution_order);
    }
}

main();
