#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
if [ "$(uname -s)" != 'Darwin' ]; then
    echo 'Сборка .app должна выполняться на macOS.' >&2
    exit 1
fi
python3 -m PyInstaller --noconfirm --clean --windowed --name 'Stone Production' \
    --osx-bundle-identifier 'com.stoneproduction.calculator' \
    --add-data 'static:static' --add-data 'data:data' \
    --hidden-import app --hidden-import uvicorn.logging \
    --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto \
    --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan.on \
    --collect-submodules uvicorn desktop.py
mkdir -p macos-output
ditto -c -k --sequesterRsrc --keepParent 'dist/Stone Production.app' "macos-output/Stone-Production-macOS-$(uname -m).zip"
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT
ditto 'dist/Stone Production.app' "$STAGING_DIR/Stone Production.app"
ln -s /Applications "$STAGING_DIR/Applications"
hdiutil create -volname 'Stone Production' -srcfolder "$STAGING_DIR" -ov -format UDZO "macos-output/Stone-Production-macOS-$(uname -m).dmg"
