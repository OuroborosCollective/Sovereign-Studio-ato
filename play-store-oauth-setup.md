# Google Play Store OAuth Setup Guide

This document explains how to set up authentication for automated Play Store publishing.

## Current Status

**The workflow exists** in `.github/workflows/android-release.yml` but requires a **Service Account** to work.

## The Problem

The OAuth client file you provided (`client_secret_...json`) is an **OAuth 2.0 Client ID** for installed applications. This is designed for user authorization flows (where a user logs in via their browser).

**You cannot use this for automated Play Store publishing** because:
- It requires user interaction (not suitable for CI/CD)
- It doesn't have Play Store API permissions
- The token expires and needs renewal

## What You Need

A **Service Account** is required for GitHub Actions automation. Here's how to create one:

### Step 1: Create Service Account in Google Cloud Console

1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Select your project: `planning-with-ai-f2b84`
3. Click **+ CREATE SERVICE ACCOUNT**
4. Fill in:
   - **Service account name**: `play-store-publisher`
   - **Service account ID**: `play-store-publisher`
   - **Description**: GitHub Actions for automated Play Store releases
5. Click **CREATE AND CONTINUE**

### Step 2: Grant Play Store Access

1. In the next step, select a role
2. Search for and select: **Release Manager** (or create custom with following permissions):
   - `playabuildapp.view`
   - `playabuildapp.upload`
   - `playrelease.manage`
   - `playtrack.manage`
3. Click **DONE**

### Step 3: Create JSON Key

1. Find your new service account in the list
3. Click the **Keys** tab
4. Click **ADD KEY** → **Create new key**
5. Select **JSON** (recommended)
6. Click **CREATE** - this downloads the JSON file

### Step 4: Add to GitHub Secrets

1. Go to: https://github.com/OuroborosCollective/Sovereign-Studio-ato/settings/secrets/actions
2. Click **New repository secret**
3. **Name**: `PLAY_STORE_JSON_KEY`
4. **Value**: Paste the entire contents of the JSON file (must be valid JSON)
5. Click **Add secret**

## Service Account JSON Format

A valid Service Account key looks like this:

```json
{
  "type": "service_account",
  "project_id": "planning-with-ai-f2b84",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "play-store-publisher@planning-with-ai-f2b84.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  ...
}
```

Compare with your OAuth client (which won't work):
```json
{
  "installed": {
    "client_id": "1008626386738-...",
    // ❌ This is NOT a Service Account
  }
}
```

## OAuth Client Already Provided

Your OAuth client is stored at:
- `android/app/client_secret_1008626386738-cvg46omcgtuevek89mvbpajcmek6fo28.apps.googleusercontent.com.json`

This is kept for reference but cannot be used for Play Store publishing.

## Alternative: OAuth with User Token (Not Recommended)

If you insist on using OAuth instead of a Service Account, you would need to:
1. Get an access token with `https://www.googleapis.com/auth/androidpublisher` scope
2. Store it as a GitHub secret
3. Update the workflow to use OAuth instead of Service Account

**Problems with this approach:**
- Token expires after 1 hour
- Requires manual token refresh
- Not suitable for automated workflows

## Links

- [Google Play Publishing API](https://developers.google.com/android-publisher)
- [Service Account Setup](https://developers.google.com/play/android-publish/quickstart#service-account)
- [GitHub Actions Secrets](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions)

---

*Setup guide generated for Sovereign Studio Android release workflow*