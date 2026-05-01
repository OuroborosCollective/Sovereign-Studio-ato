const { execSync } = require('child_process');
try {
  console.log("Generating keystore...");
  execSync('keytool -genkey -v -keystore my-release-key.keystore -alias sovereign_alias -keyalg RSA -keysize 2048 -validity 10000 -storepass sovereign123 -keypass sovereign123 -dname "CN=Sovereign, OU=Dev, O=App, L=Berlin, S=Berlin, C=DE"', {stdio: 'inherit'});
  const base64 = execSync('base64 my-release-key.keystore | tr -d "\\n"').toString();
  console.log("\\n\\n=== DEIN BASE64 KEYSTORE ===");
  console.log(base64);
  console.log("==============================\\n");
} catch(e) {
  console.error("Fehler:", e.message);
}
