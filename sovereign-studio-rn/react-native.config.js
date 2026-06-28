/**
 * React Native CLI autolinking overrides for the mobile workspace.
 *
 * The current Android Detox target validates the Sovereign mobile shell and JS
 * screens. It does not require Reanimated or the native react-native-screens
 * implementation. Keeping those packages installed for package compatibility but
 * disabling their Android native autolink prevents Gradle from compiling native
 * modules that are incompatible with the currently pinned React Native/Expo
 * versions.
 */
module.exports = {
  dependencies: {
    'react-native-reanimated': {
      platforms: {
        android: null,
      },
    },
    'react-native-screens': {
      platforms: {
        android: null,
      },
    },
  },
};
