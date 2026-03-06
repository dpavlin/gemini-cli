#!/bin/bash
# Exit on error
set -e

echo "Building Gemini CLI for local testing..."

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
  echo "Installing dependencies..."
  npm install
fi

# Build all packages
echo "Building packages..."
npm run build:packages

# Make the CLI executable locally
# The bundle script generates `bundle/gemini.js` which is the bin entry.
echo "Bundling the CLI..."
npm run bundle

# Provide instructions on how to use the built version
echo ""
echo "========================================="
echo "Build complete! You can run the local CLI using:"
echo "./bundle/gemini.js"
echo ""
echo "To make it globally available on your system, you can run:"
echo "npm link"
echo "========================================="
