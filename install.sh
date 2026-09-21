#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
INSTALL_DIR="$HOME/.local/share/Linux-Chan-AI"
APPS_DIR="$HOME/.local/share/applications"

echo "=== Linux Chan AI — Installer ==="
echo ""

# Gemini API key
read -p "Enter your Gemini API key: " gemini_api_key
if [ -z "$gemini_api_key" ]; then
    echo "Error: Gemini API key is required."
    exit 1
fi

# Write .env
echo "GEMINI_API_KEY=${gemini_api_key}" > "$SCRIPT_DIR/.env"
echo ".env created."

# System dependencies (Arch Linux)
echo ""
echo "Installing system dependencies..."
sudo pacman -S --noconfirm --needed python python-pip mpg123 ffmpeg

# Python venv
echo ""
echo "Creating Python virtual environment at $VENV_DIR ..."
python3 -m venv "$VENV_DIR"

# Install Python dependencies
echo "Installing Python packages..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# Sandbox directory
mkdir -p "$HOME/Linux-Chan-AI"
echo "Sandbox directory created: ~/Linux-Chan-AI"

# Desktop entry
mkdir -p "$APPS_DIR"
cat > "$APPS_DIR/Linux-Chan-AI.desktop" <<EOF
[Desktop Entry]
Version=2.0
Type=Application
Name=Linux Chan AI
Comment=Launch Linux Chan AI Chat
Exec=$VENV_DIR/bin/python3 $SCRIPT_DIR/linux-chan.py
Icon=$SCRIPT_DIR/icons/arch-chan_mini.png
Terminal=false
Categories=AI;Utility;
EOF

chmod +x "$APPS_DIR/Linux-Chan-AI.desktop"
echo "Desktop entry installed: $APPS_DIR/Linux-Chan-AI.desktop"

echo ""
echo "=== Installation complete! ==="
echo "Run directly: $VENV_DIR/bin/python3 $SCRIPT_DIR/linux-chan.py"
echo "Or launch from your application menu: Linux Chan AI"
