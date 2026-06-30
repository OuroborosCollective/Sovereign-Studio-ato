interface KVNamespace {
  get<T = unknown>(key: string, type: 'json'): Promise<T | null>;
  get(key: string, type?: 'text'): Promise<string | null>;
  put(
    key: string,
    value: string | ArrayBuffer | ArrayBufferView | ReadableStream,
    options?: { expirationTtl?: number; metadata?: unknown },
  ): Promise<void>;
  delete(key: string): Promise<void>;
}

interface AnalyticsEngineDataset {
  writeDataPoint(event?: {
    blobs?: string[];
    doubles?: number[];
    indexes?: string[];
  }): void;
}
