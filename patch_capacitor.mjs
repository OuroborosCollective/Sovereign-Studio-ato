import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Patches a file by replacing occurrences of a string.
 * Uses split/join instead of regex to comply with constraints.
 * 
 * @param {string} filePath 
 * @param {string} search 
 * @param {string} replacement 
 */
export const patchFile = (filePath, search, replacement) => {
  const fullPath = path.resolve(process.cwd(), filePath);

  if (!fs.existsSync(fullPath)) {
    console.warn(`File not found: ${fullPath}`);
    return;
  }

  try {
    const originalContent = fs.readFileSync(fullPath, 'utf8');
    
    if (originalContent.includes(search)) {
      // Avoid .replace(/.../g) - using split/join for global replacement
      const updatedContent = originalContent.split(search).join(replacement);
      
      fs.writeFileSync(fullPath, updatedContent, 'utf8');
      console.log(`Successfully patched: ${filePath}`);
    } else {
      console.log(`Search string not found in: ${filePath}`);
    }
  } catch (error) {
    console.error(`Error patching file ${filePath}:`, error.message);
  }
};

const runPatch = () => {
  // Example: Patching Android build.gradle or similar Capacitor configs
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

// Execution check
if (process.argv[1] === __filename) {
  runPatch();
}