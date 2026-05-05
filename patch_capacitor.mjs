import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __filename = fileURLToPath(import.meta.url);

/**
 * Patches a file by replacing occurrences of a string.
 * Uses WHATWG URL API ('new URL()') for path resolution to comply with DEP0169.
 * 
 * @param {string} filePath - Path relative to the project root
 * @param {string} search - The string to be replaced
 * @param {string} replacement - The new string
 */
export const patchFile = (filePath, search, replacement) => {
  // Use WHATWG URL API instead of deprecated url.parse()
  const projectRoot = pathToFileURL(process.cwd() + path.sep);
  const targetUrl = new URL(filePath, projectRoot);
  const fullPath = fileURLToPath(targetUrl);

  if (!fs.existsSync(fullPath)) {
    console.warn(`[Sovereign Studio] File not found: ${fullPath}`);
    return;
  }

  try {
    const originalContent = fs.readFileSync(fullPath, 'utf8');
    
    if (originalContent.includes(search)) {
      // split/join logic used to avoid restricted .replace(/.../g) regex usage
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

/**
 * Executes defined patches for Sovereign Studio V3 Capacitor environment.
 * Optimized for Capacitor 6 and modern Android/iOS build standards.
 */
const runPatch = () => {
  const patches = [
    {
      file: 'android/build.gradle',
      search: 'com.android.tools.build:gradle:8.0.0',
      replace: 'com.android.tools.build:gradle:8.2.1'
    },
    {
      file: 'android/gradle/wrapper/gradle-wrapper.properties',
      search: 'gradle-8.0-bin.zip',
      replace: 'gradle-8.2.1-bin.zip'
    },
    {
      file: 'ios/App/App.xcodeproj/project.pbxproj',
      search: 'IPHONEOS_DEPLOYMENT_TARGET = 13.0',
      replace: 'IPHONEOS_DEPLOYMENT_TARGET = 14.0'
    }
  ];

  patches.forEach(p => patchFile(p.file, p.search, p.replace));
};

if (process.argv[1] === __filename) {
  runPatch();
}