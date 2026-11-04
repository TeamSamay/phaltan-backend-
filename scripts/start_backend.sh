#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
echo "==================================================="
echo "  Starting SUTRA Backend with MongoDB & FastAPI"
echo "==================================================="
python3 scripts/run_backend.py --port 8000 --reload
