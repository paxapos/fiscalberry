#!/bin/bash

# Set the path to your Buildozer spec file
SPEC_FILE="path/to/your/buildozer.spec"

# Clean previous build artifacts
buildozer clean

# Build the APK
buildozer android debug

# Check if the build was successful
if [ -f "$SPEC_FILE" ]; then
    echo "APK built successfully!"
else
    echo "Failed to build APK."
fi