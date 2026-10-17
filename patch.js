const fs = require('fs');
const content = fs.readFileSync('src/predictive/pipeline/tickWindow.ts', 'utf8');
console.log(content.match(/function computeTickRanges[\s\S]*?return ranges;\n}/)[0]);
console.log(content.match(/export function\* generateOverlappingTickWindows[\s\S]*?startIdx \+= config.windowSize - config.overlap;\n  }\n}/)[0]);
