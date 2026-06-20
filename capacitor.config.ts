import { CapacitorConfig } from '@capacitor/cli';

function envValue(name: string): string | undefined {
  const value = process.env[name]?.trim();
  if (!value || value.startsWith('REPLACE_WITH_')) return undefined;
  return value;
}

const googleClientId = envValue('VITE_GOOGLE_CLIENT_ID');
const googleAndroidClientId = envValue('VITE_GOOGLE_ANDROID_CLIENT_ID');
const googleServerClientId = envValue('VITE_GOOGLE_SERVER_CLIENT_ID');

const config: CapacitorConfig = {
  appId: 'com.arestudio.nocode.aab',
  appName: 'NOCode Studio',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
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
      forceCodeForRefreshToken: true,
      ...(googleClientId ? { clientId: googleClientId } : {}),
      ...(googleAndroidClientId ? { androidClientId: googleAndroidClientId } : {}),
      ...(googleServerClientId ? { serverClientId: googleServerClientId } : {}),
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
