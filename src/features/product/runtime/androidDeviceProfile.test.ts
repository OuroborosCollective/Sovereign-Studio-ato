import { describe, expect, it } from 'vitest';
import { classifyAndroidViewport } from './androidDeviceProfile';

describe('androidDeviceProfile', () => {
  it('classifies narrow portrait phones as compact one-column shells', () => {
    const profile = classifyAndroidViewport({ width: 360, height: 780, devicePixelRatio: 3 });

    expect(profile.kind).toBe('phone');
    expect(profile.orientation).toBe('portrait');
    expect(profile.columns).toBe(1);
    expect(profile.navColumns).toBe(2);
    expect(profile.heightClass).toBe('regular-height');
    expect(profile.densityClass).toBe('compact-ui');
    expect(profile.className).toContain('device-phone');
    expect(profile.className).toContain('nav-2');
  });

  it('classifies landscape phones as scroll-first wide navigation shells', () => {
    const profile = classifyAndroidViewport({ width: 844, height: 390, devicePixelRatio: 2.75 });

    expect(profile.kind).toBe('phone');
    expect(profile.orientation).toBe('landscape');
    expect(profile.heightClass).toBe('compact-height');
    expect(profile.columns).toBe(1);
    expect(profile.navColumns).toBe(8);
    expect(profile.className).toContain('is-landscape');
  });

  it('classifies foldables and small tablets without forcing desktop layout', () => {
    const profile = classifyAndroidViewport({ width: 600, height: 960, devicePixelRatio: 2 });

    expect(profile.kind).toBe('foldable');
    expect(profile.columns).toBe(1);
    expect(profile.navColumns).toBe(4);
    expect(profile.maxContentWidth).toBe(920);
  });

  it('classifies tablets as two-column capable but still Android-aware', () => {
    const profile = classifyAndroidViewport({ width: 820, height: 1180, devicePixelRatio: 2 });

    expect(profile.kind).toBe('tablet');
    expect(profile.orientation).toBe('portrait');
    expect(profile.columns).toBe(2);
    expect(profile.navColumns).toBe(6);
    expect(profile.maxContentWidth).toBe(1180);
  });

  it('guards invalid viewport data with safe defaults', () => {
    const profile = classifyAndroidViewport({ width: Number.NaN, height: 0, devicePixelRatio: -1 });

    expect(profile.kind).toBe('phone');
    expect(profile.orientation).toBe('portrait');
    expect(profile.navColumns).toBe(2);
  });
});
