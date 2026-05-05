#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-$HOME/desk_matrix_64x64}"

echo "Installing apt packages..."
sudo apt update
sudo apt install -y python3-venv python3-pip python3-pil fonts-dejavu-core git curl

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

if [ ! -d venv ]; then
  python3 -m venv venv
fi

source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f config.json ]; then
  cp config.example.json config.json
fi

echo "Done. Edit $PROJECT_DIR/config.json, then run:"
echo "sudo -E env PATH=$PROJECT_DIR/venv/bin:\$PATH $PROJECT_DIR/venv/bin/python $PROJECT_DIR/main.py"
