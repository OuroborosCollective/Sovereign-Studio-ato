const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, 'src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx');
let content = fs.readFileSync(filePath, 'utf8');

// Add Loader2 import
content = content.replace(
  "import { Blocks, Bot, BrainCircuit, Cpu, Send, Square, Terminal, User, Wrench } from 'lucide-react';",
  "import { Blocks, Bot, BrainCircuit, Cpu, Loader2, Send, Square, Terminal, User, Wrench } from 'lucide-react';"
);

// Add text-left to the two other buttons
content = content.replace(
  /className="min-h-9 rounded-md bg-\[var\(--carbon-surface\)\] border border-white\/5 hover:border-\[rgba\(255,30,56,0\.3\)\] px-2/g,
  'className="min-h-9 rounded-md bg-[var(--carbon-surface)] border border-white/5 hover:border-[rgba(255,30,56,0.3)] text-left px-2'
);

// Add Loader2 to ABORT button
content = content.replace(
  /<Square size=\{10\} \/>/g,
  "{isAborting ? <Loader2 size={10} className=\"animate-spin\" /> : <Square size={10} />}"
);

// Add Loader2 to DISPATCH button
content = content.replace(
  /<Send size=\{11\} \/>/g,
  "{executing ? <Loader2 size={11} className=\"animate-spin\" /> : <Send size={11} />}"
);

// Also let's ensure we didn't mess up.
fs.writeFileSync(filePath, content);
console.log('Patched');
