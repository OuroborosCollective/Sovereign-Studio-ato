declare module '@capacitor/device' {
  export interface DeviceInfo {
    /**
     * The name of the device. For example, "John's iPhone".
     *
     * Only available on iOS and Android.
     *
     * @since 1.0.0
     */
    name?: string;

    /**
     * The device model. For example, "iPhone13,4".
     *
     * @since 1.0.0
     */
    model: string;

    /**
     * The device platform (e.g. ios, android, web).
     *
     * @since 1.0.0
     */
    platform: 'ios' | 'android' | 'web';

    /**
     * The operating system of the device.
     *
     * @since 1.0.0
     */
    operatingSystem: 'ios' | 'android' | 'windows' | 'mac' | 'unknown';

    /**
     * The version of the operating system.
     *
     * @since 1.0.0
     */
    osVersion: string;

    /**
     * The manufacturer of the device.
     *
     * @since 1.0.0
     */
    manufacturer: string;

    /**
     * Whether the device is testing in a simulator or emulator.
     *
     * @since 1.0.0
     */
    isVirtual: boolean;

    /**
     * The web view version.
     *
     * @since 1.0.0
     */
    webViewVersion: string;
  }

  export interface DeviceId {
    /**
     * The identifier of the device.
     *
     * @since 1.0.0
     */
    identifier: string;
  }

  export interface DeviceBatteryInfo {
    /**
     * The battery level of the device (0.0 to 1.0).
     *
     * @since 1.0.0
     */
    batteryLevel?: number;

    /**
     * Whether the device is charging.
     *
     * @since 1.0.0
     */
    isCharging?: boolean;
  }

  export interface DeviceLanguageCode {
    /**
     * The language code of the device.
     *
     * @since 1.0.0
     */
    value: string;
  }

  export interface DevicePlugin {
    /**
     * Return a unique identifier for the device.
     *
     * @since 1.0.0
     */
    getId(): Promise<DeviceId>;

    /**
     * Return information about the device.
     *
     * @since 1.0.0
     */
    getInfo(): Promise<DeviceInfo>;

    /**
     * Return information about the battery.
     *
     * @since 1.0.0
     */
    getBatteryInfo(): Promise<DeviceBatteryInfo>;

    /**
     * Return the language code of the device.
     *
     * @since 1.0.0
     */
    getLanguageCode(): Promise<DeviceLanguageCode>;

    /**
     * Return the language tag of the device.
     *
     * @since 1.0.0
     */
    getLanguageTag(): Promise<DeviceLanguageCode>;
  }

  const Device: DevicePlugin;
  export { Device };
}