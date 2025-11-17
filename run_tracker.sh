#!/bin/bash
# Launcher script that activates venv and runs tracker.py

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Warning: .venv directory not found. Running without virtual environment."
fi

# Run the tracker script
python3 tracker.py "$@"

