import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Patches a file by replacing occurrences of a string.
 * Uses split/join instead of regex to comply with NOCode Studio constraints.
 * 
 * @param {string} filePath 
 * @param {string} search 
 * @param {string} replacement 
 */
export const patchFile = (filePath, search, replacement) => {
  const fullPath = path.resolve(process.cwd(), filePath);

  if (!fs.existsSync(fullPath)) {
    console.warn(`[NOCode Studio] File not found: ${fullPath}`);
    return;
  }

  try {
    const originalContent = fs.readFileSync(fullPath, 'utf8');
    
    if (originalContent.includes(search)) {
      // Constraint: Never use .replace(//g) - split/join handles global replacement safely
      const updatedContent = originalContent.split(search).join(replacement);
      
      fs.writeFileSync(fullPath, updatedContent, 'utf8');
      console.log(`[NOCode Studio] Successfully patched: ${filePath}`);
    } else {
      console.log(`[NOCode Studio] Search string not found in: ${filePath}`);
    }
  } catch (error) {
    console.error(`[NOCode Studio] Error patching file ${filePath}:`, error.message);
  }
};

/**
 * Configuration for Capacitor 6 / Android SDK 34 / iOS 13+ migration patches.
 */
const runPatch = () => {
  const patches = [
    {
      file: 'android/build.gradle',
      search: 'com.android.tools.build:gradle:8.2.1',
      replace: 'com.android.tools.build:gradle:8.3.0'
    },
    {
      file: 'android/app/build.gradle',
      search: 'targetSdkVersion 33',
      replace: 'targetSdkVersion 34'
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
 * Execution check using modern WHATWG URL API to resolve DEP0169.
 * Ensures the script only runs when executed directly.
 * Replaces any legacy url.parse logic with standard URL comparisons.
 */
const isMainModule = () => {
  if (!process.argv[1]) return false;
  try {
    // Resolve absolute path and convert to file:// URL string
    const scriptURL = pathToFileURL(fs.realpathSync(process.argv[1])).href;
    // import.meta.url is already a compliant WHATWG URL string
    const currentURL = new URL(import.meta.url).href;
    
    return scriptURL === currentURL;
  } catch (e) {
    return false;
  }
};

if (isMainModule()) {
  runPatch();
}