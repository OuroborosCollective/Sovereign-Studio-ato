# Beta Testing and Marketing Information

- **Beta Testers Needed:** 14 active beta testers to use the app for 14 days (to pass Google Play Store requirements).
- **Number of Posts Created:** 3 distinct posts:
  1. A short, punchy tweet (Twitter/X style) with relevant hashtags.
  2. A slightly longer, community-focused post suitable for Reddit (e.g., r/AppIdeas, r/SideProject, r/BetaTesters).
  3. An engaging, visually descriptive post for Facebook Groups or LinkedIn.
- **Path to Generated Posts:** The generated posts are saved as markdown files to the directory `marketing-output/marketing-posts-[timestamp].md` relative to the project root.

# Recent Fixes, Patches, and Upgrades

Here is a summary of recent updates and the developers who made them:

### Ouro (New Features & Upgrades)
- **Feature:** Automated marketing engine for NOCode Studio beta distribution
- **Upgrade:** Sovereign Architect Upgrade
- **Fixes:** Sovereign AI Fixes

### google-labs-jules[bot] (Refactors, Fixes & Tests)
- **Refactors:** Consolidated duplicate UI components and refactored the `useBilling` hook to use Redux state.
- **Fixes:**
  - Fixed syntax errors in `App.tsx` regex replacements.
  - Fixed CI checks by installing `octokit` and `diff`.
  - Fixed Android Gradle build and resource errors.
  - Fixed Gradle Wrapper Jar validation failure and disabled gradle wrapper validation in CI.
  - Fixed android gradle wrapper jar checksum error.
- **Tests:** Added tests for `storageService` token expiration, `NativeStorageProvider`, and `PaywallModal` subscription handler.
