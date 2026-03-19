#!/usr/bin/env bash
# Build script for macOS — produces WhatsAppBulkMessenger.dmg in dist/
set -e

APP_NAME="WhatsAppBulkMessenger"
DMG_NAME="${APP_NAME}.dmg"
DIST_DIR="dist"
VENV_DIR=".venv"

echo "==> Setting up virtual environment..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

echo "==> Installing build dependencies..."
pip install -r requirements-dev.txt

[ -f contacts.example.csv ] || { echo "ERROR: contacts.example.csv not found. Cannot bundle sample file."; exit 1; }

echo "==> Cleaning previous build..."
rm -rf build "${DIST_DIR}/${APP_NAME}" "${DIST_DIR}/${APP_NAME}.app" "${DIST_DIR}/${DMG_NAME}"

echo "==> Building .app with PyInstaller..."
python3 -m PyInstaller \
    --windowed \
    --name "${APP_NAME}" \
    --collect-data customtkinter \
    --add-data "message.txt:." \
    --add-data "contacts.example.csv:." \
    app.py

echo "==> Creating .dmg..."
hdiutil create \
    -volname "WhatsApp Bulk Messenger" \
    -srcfolder "${DIST_DIR}/${APP_NAME}.app" \
    -ov \
    -format UDZO \
    "${DIST_DIR}/${DMG_NAME}"

echo ""
echo "Done! DMG is at: ${DIST_DIR}/${DMG_NAME}"
