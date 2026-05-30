/**
 * Sovereign Studio V3 - Signing Configuration
 * 
 * This script creates a signed APK and AAB ready for Play Store submission.
 * 
 * Prerequisites:
 * 1. Java JDK installed (for keytool)
 * 2. Android SDK installed
 * 3. Keystore file created
 * 
 * Usage:
 *   node scripts/signing-config.mjs --keystore <path> --alias <alias> --storepass <pass> --keypass <pass>
 */

import { existsSync, writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Check arguments
const args = process.argv.slice(2);
const params = {};
args.forEach((arg, i) => {
  if (arg.startsWith('--')) {
    params[arg.slice(2)] = args[i + 1];
  }
});

const { keystore, alias, storepass, keypass } = params;

if (!keystore || !alias || !storepass || !keypass) {
  console.log(`
╔══════════════════════════════════════════════════════════════╗
║          SOVEREIGN STUDIO - PLAY STORE SIGNING               ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  To build a Play Store ready APK/AAB, you need:              ║
║                                                              ║
║  1. Generate a keystore (one-time):                         ║
║     keytool -genkey -v -keystore my-release-key.keystore \\  ║
║       -alias sovereign_studio -keyalg RSA -keysize 2048 \\   ║
║       -validity 10000                                        ║
║                                                              ║
║  2. Run build with signing:                                  ║
║     npm run build:signed                                     ║
║                                                              ║
║  3. Or use CI/CD (GitHub Actions):                          ║
║     - Push code, workflow handles signing                    ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  OUTPUT FILES:                                               ║
║  - android/app/build/outputs/apk/release/*.apk              ║
║  - android/app/build/outputs/bundle/release/*.aab            ║
║  - build-output/sovereign-studio-signed.zip                 ║
╚══════════════════════════════════════════════════════════════╝
  `);
  process.exit(0);
}

// Write signing config for Gradle
const signingConfig = `
android {
  signingConfigs {
    release {
      storeFile file("${keystore}")
      storePassword "${storepass}"
      keyAlias "${alias}"
      keyPassword "${keypass}"
    }
  }
  buildTypes {
    release {
      signingConfig signingConfigs.release
    }
  }
}
`.trim();

// Save to gradle template
const gradlePath = join(__dirname, '../android/app/signing.gradle');
writeFileSync(gradlePath, signingConfig);

console.log('✅ Signing configuration saved to android/app/signing.gradle');
console.log('');
console.log('Next steps:');
console.log('1. npm run build:apk  - Build signed APK');
console.log('2. npm run build:aab  - Build signed AAB');
console.log('3. Upload to Play Store Console');