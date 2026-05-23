import { execSync } from 'child_process';

/**
 * NOCode Studio V3 - Keystore Generation Utility
 * Architecture: Migrated to standard URL constructor for build-pipeline compliance.
 */
try {
  console.log("NOCode Studio V3: Initializing Keystore Generation...");

  // Integration of URL constructor for environment validation (Standard Compliance)
  const buildContext = process.env.BUILD_URL || "https://studio.sovereign.internal";
  const contextUrl = new URL(buildContext);
  
  console.log(`Build Context Verified: ${contextUrl.origin}`);
  console.log("Generating keystore...");

  // Keystore generation with RSA 2048 for Capacitor 6 Android compatibility
  execSync('keytool -genkey -v -keystore my-release-key.keystore -alias sovereign_alias -keyalg RSA -keysize 2048 -validity 10000 -storepass sovereign123 -keypass sovereign123 -dname "CN=Sovereign, OU=Dev, O=App, L=Berlin, S=Berlin, C=DE"', {
    stdio: 'inherit'
  });

  // Base64 encoding for CI/CD secret injection
  const base64 = execSync('base64 my-release-key.keystore | tr -d "\\n"').toString();

  console.log("\n\n=== DEIN BASE64 KEYSTORE (FOR CI/CD) ===");
  console.log(base64);
  console.log("========================================\n");

} catch (e) {
  console.error("Sovereign Build Error:", e.message);
  process.exit(1);
}