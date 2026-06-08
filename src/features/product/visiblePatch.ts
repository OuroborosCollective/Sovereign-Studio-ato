export type VisiblePatch = {
  path: string;
  text: string;
  reason: string;
};

export function makeVisiblePatch(path: string, text: string, reason = 'editor-change'): VisiblePatch {
  return { path, text, reason };
}

export function patchIsSafe(patch: VisiblePatch): boolean {
  return patch.text.trim().length > 0 && !patch.text.includes('<<<<<<<');
}
