import { CapacitorConfig } from '@capacitor/cli';

const googleWebClientId = process.env.VITE_GOOGLE_CLIENT_ID;
const googleAndroidClientId = process.env.VITE_GOOGLE_ANDROID_CLIENT_ID;
const googleServerClientId = process.env.VITE_GOOGLE_SERVER_CLIENT_ID;

const googleAuthConfig = googleWebClientId
  ? {
      scopes: ['profile', 'email'],
      clientId: googleWebClientId,
      androidClientId: googleAndroidClientId ?? googleWebClientId,
      serverClientId: googleServerClientId ?? googleWebClientId,
      forceCodeForRefreshToken: true,
    }
  : undefined;

const config: CapacitorConfig = {
  appId: 'com.sovereign.studio',
  appName: 'Sovereign Studio',
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
    SplashScreen: {
      launchShowDuration: 1500,
      showSpinner: true,
      backgroundColor: '#f4f4f4',
      androidScaleType: 'CENTER_CROP',
      splashFullScreen: true,
      splashImmersive: true,
      useDialog: false,
    },
    ...(googleAuthConfig ? { GoogleAuth: googleAuthConfig } : {}),
  },
};

export default config;
