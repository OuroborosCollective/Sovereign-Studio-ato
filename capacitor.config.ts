import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.sovereign.studio',
  appName: 'Sovereign Studio',
  webDir: 'dist',
  bundledWebRuntime: false,
  server: {
    androidScheme: 'https',
    allowNavigation: [
      '*'
    ]
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1500,
      showSpinner: true,
      backgroundColor: '#f4f4f4',
      androidScaleType: 'CENTER_CROP',
      splashFullScreen: true,
      splashImmersive: true
    },
    GoogleAuth: {
      scopes: ['profile', 'email'],
      clientId: 'YOUR_WEB_CLIENT_ID.apps.googleusercontent.com',
      androidClientId: 'YOUR_ANDROID_CLIENT_ID.apps.googleusercontent.com',
      serverClientId: 'YOUR_SERVER_CLIENT_ID.apps.googleusercontent.com',
      forceCodeForRefreshToken: true
    }
  }
};

export default config;