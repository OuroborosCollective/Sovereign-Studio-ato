#!/bin/bash
set -e

echo "Fixing Gradle Kotlin version incompatibility..."

# Define the target gradle-wrapper.properties file
GRADLE_WRAPPER_PROPS="sovereign-studio-rn/android/gradle/wrapper/gradle-wrapper.properties"

if [ -f "$GRADLE_WRAPPER_PROPS" ]; then
  echo "Downgrading Gradle to 8.10.2 for Kotlin 1.9.x compatibility..."
  sed -i 's/gradle-9.3.1-bin.zip/gradle-8.10.2-bin.zip/g' "$GRADLE_WRAPPER_PROPS"
else
  echo "Warning: $GRADLE_WRAPPER_PROPS not found. Prebuild might not have run yet."
fi
