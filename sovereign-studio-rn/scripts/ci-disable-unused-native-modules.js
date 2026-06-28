const fs = require('node:fs');
const path = require('node:path');

/**
 * CI/mobile native compatibility guard.
 *
 * The current Sovereign Studio RN app uses a local JS-only navigator and does not
 * import react-native-reanimated or react-native-screens from app code. Expo
 * prebuild still lets the React Native Gradle autolinker discover their Android
 * native projects from node_modules. Those pinned native sources are currently
 * incompatible with the pinned React Native/Expo Android API and fail before E2E
 * tests can start.
 *
 * Keep the packages installed for dependency compatibility, but remove only their
 * Android native project folders after npm ci/install. The JS packages remain
 * available, while Gradle has no unused native module to compile.
 */
const UNUSED_ANDROID_MODULES = [
  'react-native-reanimated',
  'react-native-screens',
];

for (const packageName of UNUSED_ANDROID_MODULES) {
  const androidDir = path.join(__dirname, '..', 'node_modules', packageName, 'android');

  if (!fs.existsSync(androidDir)) {
    console.log(`[native-guard] ${packageName}: no Android native project present`);
    continue;
  }

  fs.rmSync(androidDir, { recursive: true, force: true });
  console.log(`[native-guard] ${packageName}: Android native project disabled`);
}
