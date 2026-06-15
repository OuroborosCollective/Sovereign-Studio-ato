#!/bin/bash
set -e

echo "Fixing Gradle Kotlin version incompatibility..."

# Define the target gradle-wrapper.properties file
GRADLE_WRAPPER_PROPS="sovereign-studio-rn/android/gradle/wrapper/gradle-wrapper.properties"
BUILD_GRADLE="sovereign-studio-rn/android/build.gradle"

if [ -f "$GRADLE_WRAPPER_PROPS" ]; then
  echo "Downgrading Gradle to 8.10.2 for Kotlin compatibility..."
  sed -i 's/gradle-9.3.1-bin.zip/gradle-8.10.2-bin.zip/g' "$GRADLE_WRAPPER_PROPS"
else
  echo "Warning: $GRADLE_WRAPPER_PROPS not found."
fi

if [ -f "$BUILD_GRADLE" ]; then
  echo "Updating Kotlin version in $BUILD_GRADLE..."
  # Try to find and replace kotlinVersion in build.gradle
  # It might be in ext block
  sed -i "s/kotlinVersion = .*/kotlinVersion = '2.1.20'/g" "$BUILD_GRADLE"
  sed -i "s/kotlin_version = .*/kotlin_version = '2.1.20'/g" "$BUILD_GRADLE"

  # Ensure we also check for the new namespace syntax if present
  if ! grep -q "kotlinVersion =" "$BUILD_GRADLE"; then
     echo "Could not find kotlinVersion, attempting to inject into ext block..."
     sed -i "/ext {/a \        kotlinVersion = '2.1.20'" "$BUILD_GRADLE"
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
