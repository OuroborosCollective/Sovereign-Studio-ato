const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, 'src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx');
let content = fs.readFileSync(filePath, 'utf8');

// Add Loader2 to DISPATCH button
content = content.replace(
  /<Send size=\{11\} \/>/g,
  "{executing ? <Loader2 size={11} className=\"animate-spin\" /> : <Send size={11} />}"
);

fs.writeFileSync(filePath, content);
console.log('Patched');
