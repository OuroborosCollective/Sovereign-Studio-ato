import sys

file_path = 'src/features/canvas/CanvasEngine.tsx'
with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # Fix the forEach missing );
    if 'fabricObjectsMap.set(fObj.id, fObj);' in line:
        new_lines.append(line)
        continue
    if 'fabricObjectsMap.delete(fObj.id);' in line:
        new_lines.append(line)
        continue

    # We'll do a more surgical replacement
    new_lines.append(line)

# This is getting complicated with just strings. Let's use a more direct approach.
