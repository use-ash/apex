#!/bin/bash
# Double-click this file in Finder to start Apex setup.
# It opens Terminal.app and runs the installer.

cd "$(dirname "$0")"
./install.sh
STATUS=$?

if [ $STATUS -ne 0 ] && [ $STATUS -ne 130 ]; then
    echo ""
    echo "  Setup exited with an error. This window will stay open."
    echo "  Press any key to close."
    read -n 1 -s
fi
