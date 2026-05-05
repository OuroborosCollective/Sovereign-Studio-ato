import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Patches a file by replacing occurrences of a string.
 * Uses split/join instead of regex to comply with Sovereign Studio constraints.
 * 
 * @param {string} filePath 
 * @param {string} search 
 * @param {string} replacement 
 */
export const patchFile = (filePath, search, replacement) => {
  // Path resolution using standard path utilities
  const fullPath = path.resolve(process.cwd(), filePath);

  if (!fs.existsSync(fullPath)) {
    console.warn(`[Sovereign Studio] File not found: ${fullPath}`);
    return;
  }

  try {
    const originalContent = fs.readFileSync(fullPath, 'utf8');
    
    if (originalContent.includes(search)) {
      // Constraint: Never use .replace(//g) - split/join handles global replacement safely
      const updatedContent = originalContent.split(search).join(replacement);
      
      fs.writeFileSync(fullPath, updatedContent, 'utf8');
      console.log(`[Sovereign Studio] Successfully patched: ${filePath}`);
    } else {
      console.log(`[Sovereign Studio] Search string not found in: ${filePath}`);
    }
  } catch (error) {
    console.error(`[Sovereign Studio] Error patching file ${filePath}:`, error.message);
  }
};

const runPatch = () => {
  const patches = [
    {
      file: 'android/build.gradle',
      search: 'com.android.tools.build:gradle:7.2.1',
      replace: 'com.android.tools.build:gradle:8.0.0'
    },
    {
      file: 'ios/App/App.xcodeproj/project.pbxproj',
      search: 'IPHONEOS_DEPLOYMENT_TARGET = 12.0',
      replace: 'IPHONEOS_DEPLOYMENT_TARGET = 13.0'
    }
  ];

  patches.forEach(p => patchFile(p.file, p.search, p.replace));
};

/**
 * Execution check using WHATWG URL API to resolve DEP0169.
 * Replaces deprecated url.parse() logic with modern URL comparison.
 */
const isMainModule = () => {
  if (!process.argv[1]) return false;
  try {
    const scriptPath = new URL(`file://${process.argv[1]}`).href;
    return scriptPath === import.meta.url;
  } catch (e) {
    return process.argv[1] === __filename;
  }
};

if (isMainModule()) {
  runPatch();
}