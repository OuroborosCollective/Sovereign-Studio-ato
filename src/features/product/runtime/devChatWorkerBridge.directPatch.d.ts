import './devChatWorkerBridge';

declare module './devChatWorkerBridge' {
  interface DevChatRepoSnapshot {
    /**
     * Optional precomputed blob path list for runtime routes that only need file paths.
     * Older snapshots may omit this; Direct GitHub Patch falls back to README.md
     * when the loaded repo tree did not expose this field.
     */
    readonly filePaths?: readonly string[];
  }
}

export {};
