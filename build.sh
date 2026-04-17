#!/usr/bin/env bash
set -e

echo "Installing build dependencies..."
pip install pyinstaller

echo "Building..."
pyinstaller TomodachiTextureTool.spec

echo ""
echo "Done! Executable is at: dist/TomodachiTextureTool"
