#!/usr/bin/env bash
# run.sh - Convenience script to launch File Fetcher with its Python environment

# Navigate to the directory containing this script
cd "$(dirname "$0")" || exit 1

# Create the virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "⚙️  Creating virtual environment in .venv..."
    python3 -m venv .venv
fi

# Activate the virtual environment
source .venv/bin/activate

# Install/update the package and its dependencies quietly
echo "📦 Installing dependencies..."
pip install -q -e .

# Launch the program with any arguments passed to this script
echo "🚀 Launching File Fetcher..."
file-fetcher "$@"
