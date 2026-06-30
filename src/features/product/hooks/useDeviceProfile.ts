/**
 * useDeviceProfile - Responsive device runtime hook
 * 
 * Detects: phone/tablet/landscape and keyboard-open state
 * Returns AndroidDeviceProfile from androidDeviceProfile.ts
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  classifyAndroidViewport,
  type AndroidDeviceProfile,
  type AndroidDeviceKind,
  type AndroidOrientation,
} from '../runtime/androidDeviceProfile';

export interface DeviceProfileInput {
  width: number;
  height: number;
  devicePixelRatio?: number;
}

export interface DeviceState {
  profile: AndroidDeviceProfile;
  isKeyboardOpen: boolean;
  keyboardHeight: number;
  isTouchDevice: boolean;
  isMobile: boolean;
  isTablet: boolean;
  isLandscape: boolean;
}

const KEYBOARD_THRESHOLD_HEIGHT = 150;

function detectKeyboardOpen(
  currentHeight: number,
  previousHeight: number,
  threshold: number = KEYBOARD_THRESHOLD_HEIGHT,
): { isOpen: boolean; height: number } {
  const heightDiff = previousHeight - currentHeight;
  if (heightDiff > threshold && currentHeight < previousHeight) {
    return { isOpen: true, height: heightDiff };
  }
  return { isOpen: false, height: 0 };
}

function getIsTouchDevice(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    'ontouchstart' in window ||
    navigator.maxTouchPoints > 0 ||
    window.matchMedia('(pointer: coarse)').matches
  );
}

export function useDeviceProfile(input?: DeviceProfileInput): DeviceState {
  const [dimensions, setDimensions] = useState<DeviceProfileInput>(() => {
    if (typeof window === 'undefined') {
      return input || { width: 390, height: 844 };
    }
    return input || {
      width: window.innerWidth,
      height: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio,
    };
  });

  const [previousHeight, setPreviousHeight] = useState(dimensions.height);
  const [keyboardState, setKeyboardState] = useState<{
    isOpen: boolean;
    height: number;
  }>({ isOpen: false, height: 0 });

  // Update dimensions on resize
  useEffect(() => {
    if (typeof window === 'undefined') return;

    let rafId: number | null = null;

    const handleResize = () => {
      // Use requestAnimationFrame to batch resize events
      if (rafId !== null) return;

      rafId = requestAnimationFrame(() => {
        rafId = null;
        const newWidth = window.innerWidth;
        const newHeight = window.innerHeight;

        setDimensions({
          width: newWidth,
          height: newHeight,
          devicePixelRatio: window.devicePixelRatio,
        });

        // Detect keyboard
        const keyboard = detectKeyboardOpen(newHeight, previousHeight);
        if (keyboard.isOpen !== keyboardState.isOpen || keyboard.height !== keyboardState.height) {
          setKeyboardState(keyboard);
          if (!keyboard.isOpen) {
            setPreviousHeight(newHeight);
          }
        }
      });
    };

    // Also detect keyboard by visual viewport API if available
    const handleVisualViewport = (event: Event) => {
      const vp = event.target as VisualViewport;
      if (!vp) return;

      const newWidth = vp.width;
      const newHeight = vp.height;
      const offsetTop = vp.offsetTop || 0;

      // Keyboard is typically open when visual viewport is smaller than layout viewport
      if (newWidth < window.innerWidth || (newHeight < window.innerHeight - KEYBOARD_THRESHOLD_HEIGHT && offsetTop > 0)) {
        const keyboardHeight = window.innerHeight - newHeight - offsetTop;
        if (keyboardHeight > KEYBOARD_THRESHOLD_HEIGHT) {
          setKeyboardState({ isOpen: true, height: keyboardHeight });
        }
      } else if (keyboardState.isOpen) {
        setKeyboardState({ isOpen: false, height: 0 });
        setPreviousHeight(window.innerHeight);
      }
    };

    window.addEventListener('resize', handleResize, { passive: true });

    const vp = window.visualViewport;
    if (vp) {
      vp.addEventListener('resize', handleVisualViewport, { passive: true });
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      if (vp) {
        vp.removeEventListener('resize', handleVisualViewport);
      }
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [previousHeight, keyboardState.isOpen, keyboardState.height]);

  // Memoize the profile calculation
  const profile = useMemo(() => {
    return classifyAndroidViewport(dimensions);
  }, [dimensions.width, dimensions.height, dimensions.devicePixelRatio]);

  // Memoize device state booleans
  const deviceState = useMemo<DeviceState>(() => {
    const isTouchDevice = getIsTouchDevice();
    const isMobile = profile.kind === 'phone' || profile.kind === 'foldable';
    const isTablet = profile.kind === 'tablet';
    const isLandscape = profile.orientation === 'landscape';

    return {
      profile,
      isKeyboardOpen: keyboardState.isOpen,
      keyboardHeight: keyboardState.height,
      isTouchDevice,
      isMobile,
      isTablet,
      isLandscape,
    };
  }, [profile, keyboardState]);

  return deviceState;
}

/**
 * Simple hook to just get device kind without full profile
 */
export function useDeviceKind(): AndroidDeviceKind {
  const { profile } = useDeviceProfile();
  return profile.kind;
}

/**
 * Simple hook to just get orientation
 */
export function useDeviceOrientation(): AndroidOrientation {
  const { profile } = useDeviceProfile();
  return profile.orientation;
}

/**
 * Simple hook to check if keyboard is open
 */
export function useKeyboardOpen(): boolean {
  const { isKeyboardOpen } = useDeviceProfile();
  return isKeyboardOpen;
}

/**
 * Hook for responsive layout decisions
 */
export interface ResponsiveLayout {
  columns: 1 | 2;
  maxWidth: number;
  fontSize: 'small' | 'medium' | 'large';
  spacing: 'compact' | 'comfortable' | 'spacious';
}

export function useResponsiveLayout(): ResponsiveLayout {
  const device = useDeviceProfile();

  return useMemo(() => {
    // Determine layout based on device profile
    const columns: 1 | 2 = device.profile.columns;
    const maxWidth = device.profile.maxContentWidth;

    // Font size based on density class
    const fontSize: ResponsiveLayout['fontSize'] =
      device.profile.densityClass === 'compact-ui' ? 'small' :
      device.profile.densityClass === 'comfortable-ui' ? 'medium' : 'medium';

    // Spacing based on height class and orientation
    const spacing: ResponsiveLayout['spacing'] =
      device.profile.heightClass === 'compact-height' ? 'compact' :
      device.isLandscape ? 'comfortable' : 'spacious';

    return { columns, maxWidth, fontSize, spacing };
  }, [device]);
}
