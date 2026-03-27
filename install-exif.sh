#!/bin/bash
# Install exiftool for EXIF metadata extraction
set -e

if command -v brew &>/dev/null; then
    echo "Installing exiftool via Homebrew..."
    brew install exiftool
else
    echo "Installing Pillow for Python EXIF reading..."
    pip3 install Pillow
fi

echo "Done. Ready to read EXIF data."
