import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.arestudio.nocode.aab',
  appName: 'NOCode Studio',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    allowNavigation: ['*'],
  },
  android: {
    backgroundColor: '#f4f4f4',
    allowMixedContent: false,
    captureInput: true,
    buildOptions: {
      releaseType: 'AAB',
    },
  },
  plugins: {
    GoogleAuth: {
      scopes: ['profile', 'email'],
      clientId: 'REPLACE_WITH_VITE_GOOGLE_CLIENT_ID',
      androidClientId: 'REPLACE_WITH_VITE_GOOGLE_ANDROID_CLIENT_ID',
      serverClientId: 'REPLACE_WITH_VITE_GOOGLE_SERVER_CLIENT_ID',
      forceCodeForRefreshToken: true,
    },
    SplashScreen: {
      launchShowDuration: 1500,
      showSpinner: true,
      backgroundColor: '#f4f4f4',
      androidScaleType: 'CENTER_CROP',
      splashFullScreen: true,
      splashImmersive: true,
      useDialog: false,
    },
  },
};

export default config;