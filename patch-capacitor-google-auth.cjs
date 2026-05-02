const fs = require('fs');
const path = require('path');

const targetFile = path.resolve(__dirname, 'node_modules/@codetrix-studio/capacitor-google-auth/android/build.gradle');

if (fs.existsSync(targetFile)) {
  let content = fs.readFileSync(targetFile, 'utf8');
  if (content.includes('jcenter()')) {
    content = content.replace(/jcenter\(\)/g, 'mavenCentral()');
    fs.writeFileSync(targetFile, content, 'utf8');
    console.log('Patched capacitor-google-auth build.gradle');
  } else {
    console.log('capacitor-google-auth build.gradle already patched');
  }
} else {
  console.log('Could not find capacitor-google-auth build.gradle');
}
