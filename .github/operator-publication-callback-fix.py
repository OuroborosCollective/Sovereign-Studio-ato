from pathlib import Path

path = Path('src/features/control-surface-vnext/components/PublicationInspector/PublicationInspector.tsx')
text = path.read_text('utf-8')
old = "  onPrepare?: () => void | Promise<void>;\n  onPublish?: () => void | Promise<void>;\n"
new = "  onPrepare?: () => void | Promise<unknown>;\n  onPublish?: () => void | Promise<unknown>;\n"
count = text.count(old)
assert count == 1, f'unexpected PublicationInspector callback contract matches: {count}'
path.write_text(text.replace(old, new, 1), 'utf-8')
