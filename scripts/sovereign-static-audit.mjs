import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const required = [
  'package.json',
  'vite.config.ts',
  'AGENTS.md',
  'sovereign.guard.json',
  'src/main.tsx',
  'src/App.tsx',
  'capacitor.config.ts',
  'android/app/build.gradle',
  'android/app/src/main/AndroidManifest.xml',
  'android/app/src/main/assets/public/index.html',
];

const strictCapacitorMajor = process.env.SOVEREIGN_STRICT_CAPACITOR_MAJOR === '1';
let ok = true;

function fail(message) {
  console.error(`[audit] ${message}`);
  ok = false;
}

function warn(message) {
  console.warn(`[audit] ${message}`);
}

function read(file) {
  return readFileSync(file, 'utf8');
}

function readJson(file) {
  return JSON.parse(read(file));
}

function versionMajor(value) {
  const match = String(value ?? '').match(/\d+/);
  return match ? Number.parseInt(match[0], 10) : null;
}

for (const file of required) {
  if (!existsSync(file)) fail(`missing: ${file}`);
}

if (existsSync('src/main.tsx')) {
  const main = read('src/main.tsx');
  if (!main.includes("import App from './App'")) fail('src/main.tsx must import the current App shell.');
  if (!main.includes('<App />')) fail('src/main.tsx must render the current App shell.');
  if (!main.includes('installMobileAgentMonitor')) fail('src/main.tsx must install the Android agent monitor runtime.');
  if (!main.includes('restoreCanvasStateMirror')) fail('src/main.tsx must restore mobile workspace persistence before boot.');
}

if (existsSync('package.json')) {
  const pkg = readJson('package.json');
  const allDeps = { ...(pkg.dependencies ?? {}), ...(pkg.devDependencies ?? {}) };
  const capacitorPackages = ['@capacitor/core', '@capacitor/android', '@capacitor/cli'];
  const majors = capacitorPackages.map((name) => [name, versionMajor(allDeps[name])]);
  const majorDetail = majors.map(([name, major]) => `${name}=${major ?? 'missing'}`).join(', ');
  const missing = majors.filter(([, major]) => major === null).map(([name]) => name);
  if (missing.length) fail(`missing Capacitor package(s): ${missing.join(', ')}`);

  const distinctMajors = new Set(majors.map(([, major]) => major).filter((major) => major !== null));
  if (distinctMajors.size > 1) {
    const message = `Capacitor major versions are not aligned yet: ${majorDetail}. Keep lockfile consistency for this release or regenerate pnpm-lock before strict enforcement.`;
    if (strictCapacitorMajor) fail(message);
    else warn(message);
  }
}

if (existsSync('capacitor.config.ts')) {
  const config = read('capacitor.config.ts');
  if (/allowNavigation\s*:\s*\[\s*['"]\*['"]\s*\]/.test(config)) {
    fail('capacitor.config.ts must not use wildcard allowNavigation for release WebView builds.');
  }
  if (/REPLACE_WITH_VITE_GOOGLE_/.test(config)) {
    fail('capacitor.config.ts must not ship placeholder GoogleAuth client IDs.');
  }
  if (!/allowMixedContent\s*:\s*false/.test(config)) fail('capacitor.config.ts must keep Android mixed content disabled.');
}

if (existsSync('android/app/build.gradle')) {
  const gradle = read('android/app/build.gradle');
  if (!gradle.includes('android.skipWebAssetBuild')) warn('android/app/build.gradle should support android.skipWebAssetBuild to avoid duplicate CI web rebuilds.');
  if (!gradle.includes('pnpm run build:web')) warn('android/app/build.gradle should prefer the pnpm web build path for Android assets.');
  if (!gradle.includes('minifyEnabled true')) fail('android release build must keep minifyEnabled true.');
  if (!gradle.includes('shrinkResources true')) fail('android release build must keep shrinkResources true.');
}

if (existsSync('android/app/src/main/AndroidManifest.xml')) {
  const manifest = read('android/app/src/main/AndroidManifest.xml');
  if (!manifest.includes('android:usesCleartextTraffic="${usesCleartextTraffic}"')) fail('manifest should use release/debug cleartext placeholder.');
  if (!/android:exported="true"/.test(manifest)) fail('launcher activity exported=true is required on modern Android.');
  if (!/android:allowBackup="false"/.test(manifest)) fail('release manifest should keep allowBackup=false.');
}

if (existsSync('android/app/src/main/assets/public/index.html')) {
  const indexPath = 'android/app/src/main/assets/public/index.html';
  const html = read(indexPath);
  const strictAssets = process.env.SOVEREIGN_STRICT_ANDROID_ASSETS === '1' || existsSync('dist/index.html');

  if (!html.includes('SOVEREIGN_BOOT_FALLBACK_V2')) fail('Android index.html must include the WebView recovery fallback.');

  const baseDir = dirname(indexPath);
  const refs = [...html.matchAll(/\b(?:src|href)=["']\.\/([^"'#?]+)/g)].map((match) => match[1]);
  const missingRefs = refs.filter((ref) => !existsSync(resolve(baseDir, ref)));

  if (missingRefs.length && strictAssets) {
    fail(`Android index.html references missing packaged asset(s): ${missingRefs.join(', ')}`);
  } else if (missingRefs.length) {
    warn(`Android index.html references asset(s) not present in checkout yet: ${missingRefs.join(', ')}. Run build:web before strict release packaging.`);
  }
}

if (!ok) process.exit(1);
console.log('[audit] Sovereign static audit passed.');
