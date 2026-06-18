export type AndroidDeviceKind = 'phone' | 'foldable' | 'tablet' | 'desktop-like';
export type AndroidOrientation = 'portrait' | 'landscape';
export type AndroidHeightClass = 'compact-height' | 'regular-height';
export type AndroidDensityClass = 'compact-ui' | 'comfortable-ui';

export interface AndroidViewportInput {
  width: number;
  height: number;
  devicePixelRatio?: number;
}

export interface AndroidDeviceProfile {
  kind: AndroidDeviceKind;
  orientation: AndroidOrientation;
  heightClass: AndroidHeightClass;
  densityClass: AndroidDensityClass;
  columns: 1 | 2;
  navColumns: 2 | 3 | 4 | 6 | 8;
  maxContentWidth: number;
  className: string;
}

function finitePositive(value: number, fallback: number): number {
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function classifyAndroidViewport(input: AndroidViewportInput): AndroidDeviceProfile {
  const width = finitePositive(input.width, 390);
  const height = finitePositive(input.height, 844);
  const dpr = finitePositive(input.devicePixelRatio ?? 1, 1);
  const shortest = Math.min(width, height);
  const longest = Math.max(width, height);
  const orientation: AndroidOrientation = width >= height ? 'landscape' : 'portrait';
  const heightClass: AndroidHeightClass = height < 620 ? 'compact-height' : 'regular-height';
  const densityClass: AndroidDensityClass = shortest < 390 || dpr >= 3 ? 'compact-ui' : 'comfortable-ui';

  let kind: AndroidDeviceKind = 'phone';
  if (shortest >= 900) kind = 'desktop-like';
  else if (shortest >= 680) kind = 'tablet';
  else if (shortest >= 540 && longest >= 720) kind = 'foldable';

  const columns: 1 | 2 = kind === 'tablet' || kind === 'desktop-like' ? 2 : 1;
  const navColumns: AndroidDeviceProfile['navColumns'] = orientation === 'landscape'
    ? 8
    : kind === 'tablet' || kind === 'desktop-like'
      ? 6
      : kind === 'foldable'
        ? 4
        : 2;
  const maxContentWidth = kind === 'phone' ? 720 : kind === 'foldable' ? 920 : 1180;

  const tokens = [
    `device-${kind}`,
    `is-${orientation}`,
    heightClass,
    densityClass,
    `nav-${navColumns}`,
    `content-${columns}-col`,
  ];

  return {
    kind,
    orientation,
    heightClass,
    densityClass,
    columns,
    navColumns,
    maxContentWidth,
    className: tokens.join(' '),
  };
}

export function currentAndroidDeviceProfile(win: Pick<Window, 'innerWidth' | 'innerHeight' | 'devicePixelRatio'> = window): AndroidDeviceProfile {
  return classifyAndroidViewport({
    width: win.innerWidth,
    height: win.innerHeight,
    devicePixelRatio: win.devicePixelRatio,
  });
}
