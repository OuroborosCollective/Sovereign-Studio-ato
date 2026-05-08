# Sovereign Studio Play Store Release

This project builds a signed Android release APK and AAB through GitHub Actions.

## Required GitHub Actions secrets

The release workflow expects exactly these repository secrets:

- `KEYSTORE_BASE64` - Base64 encoded Android keystore file.
- `KEYSTORE_ALIAS` - Alias of the signing key inside the keystore.
- `KEYSTORE_PASSWORD` - Password for the keystore.
- `KEY_PASSWORD` - Password for the signing key.

Do not commit keystore files, passwords, Play Console keys, OAuth secrets, or API tokens into the repository.

## Build a Play Store release

1. Open GitHub Actions.
2. Select **Android Release Build**.
3. Click **Run workflow**.
4. Optionally set:
   - `version_code` - must be higher than every version already uploaded to Google Play.
   - `version_name` - visible release version, for example `1.1.1`.
5. Wait until the workflow finishes.
6. Download the artifacts:
   - `SovereignStudio-playstore-release-aab` - upload this to Google Play Console.
   - `SovereignStudio-release-apk` - use this only for direct device testing.
   - `SovereignStudio-proguard-mapping` - upload to Play Console if minification is enabled.

## Google Play Console checklist

Before production submission, check these items:

- Package name is stable: `com.arestudio.nocode.aab`.
- `versionCode` is higher than previous Play uploads.
- Release artifact is the signed `.aab`, not the APK.
- App name, short description, full description, screenshots and feature graphic are present.
- App category and contact email are set.
- Privacy policy URL is configured if required by app behavior.
- Data Safety form matches the app behavior.
- Content rating questionnaire is completed.
- Target audience and ads declarations are completed.
- App access instructions are provided if login or restricted features are required.
- Internal testing track has at least one successful install before production.
- The signed AAB uses the same signing identity for future updates.

## Local verification commands

After downloading artifacts, a local machine with Android SDK can verify the APK:

```bash
apksigner verify --verbose app-release.apk
```

To inspect the AAB locally, use Android bundletool:

```bash
bundletool validate --bundle app-release.aab
```

## Notes

The release workflow uses the checked-in Gradle release signing config and passes signing values only through runtime environment variables. The decoded keystore is created inside the GitHub Actions runner and is not committed.
