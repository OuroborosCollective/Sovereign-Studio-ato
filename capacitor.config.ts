import { CapacitorConfig } from '@capacitor/cli';

function envValue(name: string): string | undefined {
  const value = process.env[name]?.trim();
  if (!value || value.startsWith('REPLACE_WITH_')) return undefined;
  return value;
}

const PUBLIC_GOOGLE_WEB_CLIENT_ID = '511695074775-s08le2ju1k4nl2vv3i150i6tn084b682.apps.googleusercontent.com';
const PUBLIC_GOOGLE_ANDROID_CLIENT_ID = '511695074775-tjlbufo0r0co0eg8rsfonma9dnnv72hl.apps.googleusercontent.com';
const googleClientId = envValue('VITE_GOOGLE_CLIENT_ID') ?? PUBLIC_GOOGLE_WEB_CLIENT_ID;
const googleAndroidClientId = envValue('VITE_GOOGLE_ANDROID_CLIENT_ID') ?? PUBLIC_GOOGLE_ANDROID_CLIENT_ID;
const googleServerClientId = envValue('VITE_GOOGLE_SERVER_CLIENT_ID') ?? PUBLIC_GOOGLE_WEB_CLIENT_ID;

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
