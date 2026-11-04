#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
echo "============================================================="
echo "  Starting SUTRA Full Stack (Backend + AI Engine + MongoDB)"
echo "============================================================="
python3 scripts/run_all.py --mode synthetic --frames 180
