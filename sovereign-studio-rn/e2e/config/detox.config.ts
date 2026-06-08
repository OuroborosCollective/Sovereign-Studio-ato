import type { DetoxConfig } from 'detox';

const configuration: Record<string, Detox.DeviceConfiguration> = {
  'android.debug': {
    type: 'android.attached',
    binaryPath: 'android/app/build/outputs/apk/debug/app-debug.apk',
    build: 'cd android && ./gradlew assembleDebug assembleAndroidTest -DtestBuildType=debug && cd ../..',
    reversePorts: [8081],
  },
  'android.release': {
    type: 'android.attached',
    binaryPath: 'android/app/build/outputs/apk/release/app-release.apk',
    build: 'cd android && ./gradlew assembleRelease assembleAndroidTest -DtestBuildType=release && cd ../..',
    reversePorts: [8081],
  },
  'ios.sim.debug': {
    type: 'ios.simulator',
    device: {
      id: 'iPhone 15 Pro',
    },
    build: 'xcodebuild -workspace ios/Runner.xcworkspace -scheme Runner -configuration Debug -sdk iphonesimulator -derivedDataPath ./ios/build',
  },
  'ios.sim.release': {
    type: 'ios.simulator',
    device: {
      id: 'iPhone 15 Pro',
    },
    build: 'xcodebuild -workspace ios/Runner.xcworkspace -scheme Runner -configuration Release -sdk iphonesimulator -derivedDataPath ./ios/build',
  },
};

const config: DetoxConfig = {
  testRunner: {
    args: {
      '$0': 'jest',
      config: 'e2e/detox/jest.config.js',
    },
    installSnapshots: true,
  },
  reporter: 'detox-testability-reporter',
  behavior: {
    init: {
      exposeGlobals: true,
    },
    launchApp: 'auto',
    reuse: true,
  },
  configurations: configuration,
};

export default config;