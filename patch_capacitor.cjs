const fs = require('fs');
const path = require('path');

const pluginBuildGradlePath = path.join(
    __dirname,
    'node_modules',
    '@codetrix-studio',
    'capacitor-google-auth',
    'android',
    'build.gradle'
);

if (fs.existsSync(pluginBuildGradlePath)) {
    let content = fs.readFileSync(pluginBuildGradlePath, 'utf8');
    content = content.replace(/jcenter\(\)/g, 'mavenCentral()');
    fs.writeFileSync(pluginBuildGradlePath, content, 'utf8');
    console.log('Patched capacitor-google-auth to remove jcenter()');
} else {
    console.log('capacitor-google-auth build.gradle not found');
}
