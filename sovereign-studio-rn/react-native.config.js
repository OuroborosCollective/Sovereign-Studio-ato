/**
 * React Native CLI autolinking overrides for the mobile workspace.
 *
 * The app does not import react-native-reanimated at runtime. Keeping the npm
 * dependency installed but disabling its Android native autolink prevents the
 * Detox debug build from compiling an incompatible Reanimated native module
 * against the currently pinned React Native/Expo versions.
 */
module.exports = {
  dependencies: {
    'react-native-reanimated': {
      platforms: {
        android: null,
      },
    },
  },
};
