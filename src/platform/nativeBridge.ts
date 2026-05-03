import { Capacitor } from '@capacitor/core';
import { PushNotifications } from '@capacitor/push-notifications';
import { NativeBiometric } from '@capacitor-community/native-biometric';

export interface NativeBridge {
  isNative: boolean;
  biometrics: {
    isAvailable: () => Promise<boolean>;
    authenticate: (reason: string, title?: string) => Promise<boolean>;
  };
  push: {
    requestPermissions: () => Promise<boolean>;
    addListener: (eventName: string, callback: (data: any) => void) => Promise<void>;
    removeAllListeners: () => Promise<void>;
  };
}

const isNative = Capacitor.isNativePlatform();

export const nativeBridge: NativeBridge = {
  isNative,

  biometrics: {
    isAvailable: async () => {
      if (!isNative) {
        return false;
      }
      try {
        const result = await NativeBiometric.isAvailable();
        return !!result.isAvailable;
      } catch (error) {
        return false;
      }
    },
    authenticate: async (reason: string, title: string = 'Authentifizierung') => {
      if (!isNative) {
        // Mock success for development/web preview
        return true; 
      }
      try {
        await NativeBiometric.verifyIdentity({
          reason,
          title,
          description: 'Bitte bestätigen Sie Ihre Identität',
        });
        return true;
      } catch (error) {
        return false;
      }
    },
  },

  push: {
    requestPermissions: async () => {
      if (!isNative) return false;
      try {
        const result = await PushNotifications.requestPermissions();
        if (result.receive === 'granted') {
          await PushNotifications.register();
          return true;
        }
        return false;
      } catch (error) {
        return false;
      }
    },
    addListener: async (eventName: string, callback: (data: any) => void) => {
      if (!isNative) return;
      try {
        await PushNotifications.addListener(eventName as any, callback);
      } catch (error) {
        console.error('Push addListener error:', error);
      }
    },
    removeAllListeners: async () => {
      if (!isNative) return;
      try {
        await PushNotifications.removeAllListeners();
      } catch (error) {
        console.error('Push removeAllListeners error:', error);
      }
    },
  },
};