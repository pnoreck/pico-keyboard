#!/bin/bash
# Launcher script that ensures a working venv and runs tracker.py

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

VENV=".venv"
PIP_ARGS="install -q --disable-pip-version-check -r requirements.txt"

# A Homebrew Python upgrade removes the interpreter the venv symlinks to,
# leaving a dangling .venv/bin/python3. Detect that and rebuild.
if [ -d "$VENV" ] && ! "$VENV/bin/python3" -c "pass" >/dev/null 2>&1; then
    echo "[VENV] Interpreter in $VENV is broken (Python upgraded?), rebuilding..."
    rm -rf "$VENV"
fi

if [ ! -d "$VENV" ]; then
    echo "[VENV] Creating $VENV with $(python3 --version)..."
    python3 -m venv "$VENV" || { echo "Failed to create venv"; exit 1; }
    "$VENV/bin/pip" $PIP_ARGS || { echo "Failed to install requirements"; exit 1; }
fi

source "$VENV/bin/activate"

# Install missing dependencies into the venv (not into whatever pip is on PATH)
if ! python3 -c "import serial, yaml" >/dev/null 2>&1; then
    echo "[VENV] Installing dependencies from requirements.txt..."
    pip $PIP_ARGS || { echo "Failed to install requirements"; exit 1; }
fi

# Run the tracker script
python3 tracker.py "$@"
