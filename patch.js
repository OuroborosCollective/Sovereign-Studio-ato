import fs from 'fs';
const filepath = 'src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx';
let code = fs.readFileSync(filepath, 'utf-8');

code = code.replace(
  '<div className="flex-1 min-h-0 overflow-y-auto p-3 sm:p-4 space-y-3" data-testid="vnext-message-stream">{messages.map((message) => <MessageCard key={message.id} message={message} />)}</div>',
  `<div className="flex-1 min-h-0 overflow-y-auto p-3 sm:p-4 space-y-3" data-testid="vnext-message-stream" role="log" aria-live="polite">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-[var(--text-dim)]">
            <Bot size={24} className="mb-2 opacity-50" />
            <p className="text-[11px] font-mono">No missions logged.</p>
            <p className="text-[9px] font-mono mt-1 opacity-75">Dispatch a mission to begin.</p>
          </div>
        ) : (
          messages.map((message) => <MessageCard key={message.id} message={message} />)
        )}
      </div>`
);
fs.writeFileSync(filepath, code);
