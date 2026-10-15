import fs from 'fs';
const filepath = 'src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx';
let code = fs.readFileSync(filepath, 'utf-8');
console.log(code.includes('messages.length === 0'));
