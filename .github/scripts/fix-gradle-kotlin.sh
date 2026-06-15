#!/bin/bash
set -e

echo "Fixing Gradle Kotlin version incompatibility..."

# Target files
GRADLE_WRAPPER_PROPS="sovereign-studio-rn/android/gradle/wrapper/gradle-wrapper.properties"
GRADLE_PROPS="sovereign-studio-rn/android/gradle.properties"
BUILD_GRADLE="sovereign-studio-rn/android/build.gradle"

# 1. Downgrade Gradle to a version compatible with Kotlin 2.1.x / 1.9.x
if [ -f "$GRADLE_WRAPPER_PROPS" ]; then
  echo "Downgrading Gradle to 8.10.2..."
  sed -i 's/gradle-[0-9.]\+-bin.zip/gradle-8.10.2-bin.zip/g' "$GRADLE_WRAPPER_PROPS"
else
  echo "Warning: $GRADLE_WRAPPER_PROPS not found."
fi

# 2. Set Kotlin version in gradle.properties
if [ -f "$GRADLE_PROPS" ]; then
  echo "Setting kotlinVersion in gradle.properties..."
  if grep -q "kotlinVersion=" "$GRADLE_PROPS"; then
    sed -i "s/kotlinVersion=.*/kotlinVersion=2.1.20/g" "$GRADLE_PROPS"
  else
    echo "kotlinVersion=2.1.20" >> "$GRADLE_PROPS"
  fi
  # Also set android.kotlinVersion just in case
  if grep -q "android.kotlinVersion=" "$GRADLE_PROPS"; then
    sed -i "s/android.kotlinVersion=.*/android.kotlinVersion=2.1.20/g" "$GRADLE_PROPS"
  else
    echo "android.kotlinVersion=2.1.20" >> "$GRADLE_PROPS"
  fi
fi

# 3. Force Kotlin version in build.gradle
if [ -f "$BUILD_GRADLE" ]; then
  echo "Updating build.gradle..."
  # Replace any variant of kotlinVersion assignment
  sed -i "s/kotlinVersion\s*=\s*.*/kotlinVersion = '2.1.20'/g" "$BUILD_GRADLE"
  sed -i "s/kotlin_version\s*=\s*.*/kotlin_version = '2.1.20'/g" "$BUILD_GRADLE"

  # Ensure we also check for the new namespace syntax if present
  if ! grep -q "kotlinVersion" "$BUILD_GRADLE"; then
     echo "kotlinVersion not found in build.gradle, attempting to inject into ext block..."
     sed -i '/ext {/a \        kotlinVersion = "2.1.20"' "$BUILD_GRADLE"
  fi
else
  echo "Warning: $BUILD_GRADLE not found."
fi

# Root android folder (Capacitor)
ROOT_BUILD_GRADLE="android/build.gradle"
if [ -f "$ROOT_BUILD_GRADLE" ]; then
  echo "Updating Kotlin version in $ROOT_BUILD_GRADLE..."
  sed -i "s/kotlinVersion = .*/kotlinVersion = '2.1.20'/g" "$ROOT_BUILD_GRADLE"
fi

echo "Kotlin/Gradle fix applied successfully."
