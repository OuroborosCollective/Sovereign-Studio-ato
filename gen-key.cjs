const { execSync } = require('child_process');
require('dotenv').config();

try {
  console.log("Sovereign Studio V3: Initializing Keystore Generation (CJS)...");

  // Securely retrieve passwords from environment variables
  const storePass = process.env.ANDROID_KEYSTORE_PASSWORD;
  const keyPass = process.env.ANDROID_KEY_PASSWORD;

  if (!storePass || !keyPass) {
    console.error("\n❌ ERROR: ANDROID_KEYSTORE_PASSWORD and ANDROID_KEY_PASSWORD must be set.");
    console.error("Please set them in your terminal or in a .env file.\n");
    process.exit(1);
  }

  console.log("Generating keystore...");

  // Keystore generation with RSA 2048 for Capacitor 6 Android compatibility
  // Using -storepass:env and -keypass:env to avoid exposing passwords in process list
  execSync('keytool -genkey -v -keystore my-release-key.keystore -alias sovereign_alias -keyalg RSA -keysize 2048 -validity 10000 -storepass:env STORE_PASS -keypass:env KEY_PASS -dname "CN=Sovereign, OU=Dev, O=App, L=Berlin, S=Berlin, C=DE"', {
    stdio: 'inherit',
    env: {
      ...process.env,
      STORE_PASS: storePass,
      KEY_PASS: keyPass
    }
  });

  const base64 = execSync('base64 my-release-key.keystore | tr -d "\\n"').toString();

  console.log("\n\n=== DEIN BASE64 KEYSTORE ===");
  console.log(base64);
  console.log("==============================\n");
} catch(e) {
  console.error("Sovereign Build Error:", e.message);
  process.exit(1);
}
