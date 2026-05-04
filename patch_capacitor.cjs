import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

/**
 * @file patch_capacitor.js
 * @description ESM-basierter Patch zur Korrektur der build.gradle-Konfiguration.
 * Ersetzt 'jcenter()' durch 'mavenCentral()' im Plugin '@codetrix-studio/capacitor-google-auth'.
 */

try {
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = path.dirname(__filename);

    const pluginBuildGradlePath = path.join(
        __dirname,
        'node_modules',
        '@codetrix-studio',
        'capacitor-google-auth',
        'android',
        'build.gradle'
    );

    if (fs.existsSync(pluginBuildGradlePath)) {
        const content = fs.readFileSync(pluginBuildGradlePath, 'utf8');

        if (content.includes('jcenter()')) {
            // Sicherer Ersatz ohne Regex-Global-Flag zur Vermeidung von Kompatibilitätsproblemen
            const updatedContent = content.split('jcenter()').join('mavenCentral()');

            if (updatedContent !== content) {
                fs.writeFileSync(pluginBuildGradlePath, updatedContent, 'utf8');
                console.log('Patch erfolgreich: jcenter() wurde durch mavenCentral() ersetzt.');
            } else {
                console.log('Keine Änderungen vorgenommen: Datei bereits im Zielzustand.');
            }
        } else {
            console.log('Patch nicht erforderlich: jcenter() wurde in der build.gradle nicht gefunden.');
        }
    } else {
        console.log('Plugin-Pfad nicht gefunden, Patch wird übersprungen: ' + pluginBuildGradlePath);
    }
} catch (error) {
    console.error('Fehler beim Ausführen des Patches:', error instanceof Error ? error.message : error);
    process.exit(0); // Verhindert Build-Abbruch bei optionalem Patch
}