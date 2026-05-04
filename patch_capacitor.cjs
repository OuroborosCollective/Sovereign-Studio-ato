/**
 * @file patch_capacitor.cjs
 * @description Dieser Patch automatisiert die Korrektur der build.gradle-Konfiguration für das Plugin
 * '@codetrix-studio/capacitor-google-auth' innerhalb der Android-Plattform.
 * 
 * Problem: Das Plugin nutzt standardmäßig 'jcenter()', welches abgekündigt ist und zu Build-Fehlern
 * in modernen Gradle-Umgebungen führt.
 * 
 * Lösung: Das Skript lokalisiert die Build-Datei im node_modules-Verzeichnis und ersetzt
 * sämtliche Instanzen von 'jcenter()' durch 'mavenCentral()', um die Build-Stabilität zu gewährleisten.
 */

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
    
    // Vermeidung von replace(//g) durch Verwendung von split/join zur Gewährleistung der Kompatibilität
    content = content.split('jcenter()').join('mavenCentral()');
    
    fs.writeFileSync(pluginBuildGradlePath, content, 'utf8');
    console.log('Patched capacitor-google-auth: Replaced jcenter() with mavenCentral()');
} else {
    console.log('capacitor-google-auth build.gradle not found, skipping patch');
}