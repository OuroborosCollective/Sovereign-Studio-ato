import './devChatWorkerBridge';

declare module './devChatWorkerBridge' {
  interface DevChatRepoSnapshot {
    /**
     * Precomputed blob path list produced by the repository tree runtime.
     */
    readonly filePaths: readonly string[];
  }
}

export {};
