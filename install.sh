#!/bin/bash
set -e

USER_NAME=$(whoami)
MOUNT_POINT="/media/plex"
LOG_PATH="/var/log/plexfs.log"
CACHE_DIR="/var/cache/plexfs"
PLEXFS_BIN="/usr/local/bin/plexfs.py"
CONFIG_FILE="/etc/plexfs.conf"
VENV_PATH="/opt/plexfs-venv"

echo "🔧 Installing PlexFS dependencies and environment..."

# Base dependencies
sudo apt update
sudo apt install -y python3 python3-venv fuse

# Create virtual environment if it doesn’t exist
if [ ! -d "$VENV_PATH" ]; then
    echo "📦 Creating Python virtual environment at $VENV_PATH..."
    sudo python3 -m venv "$VENV_PATH"
    sudo chown -R "$USER_NAME":"$USER_NAME" "$VENV_PATH"
fi

# Activate virtual environment and install Python packages
echo "📚 Installing Python dependencies..."
source "$VENV_PATH/bin/activate"
pip install --upgrade pip
pip install requests plexapi fusepy
deactivate

# Prepare directories
sudo mkdir -p "$MOUNT_POINT" "$CACHE_DIR" /var/log
sudo touch "$LOG_PATH"
sudo chown -R "$USER_NAME":"$USER_NAME" "$MOUNT_POINT" "$LOG_PATH" "$CACHE_DIR"
sudo chmod 755 "$MOUNT_POINT" "$CACHE_DIR"
sudo chmod 644 "$LOG_PATH"

# Copy scripts and config
sudo cp plexfs.py "$PLEXFS_BIN"
sudo chmod +x "$PLEXFS_BIN"

if [ ! -f "$CONFIG_FILE" ]; then
    sudo cp plexfs.conf.template "$CONFIG_FILE"
fi

# Create systemd service
echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/plexfs.service > /dev/null <<EOF
[Unit]
Description=Mount Plex Server via FUSE
After=network.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
ExecStart=$VENV_PATH/bin/python $PLEXFS_BIN
WorkingDirectory=/usr/local/bin
Restart=on-failure
RestartSec=5
LimitNOFILE=65536
Environment="PATH=$VENV_PATH/bin"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable plexfs
sudo systemctl restart plexfs

echo "✅ PlexFS installation complete!"
echo "Edit $CONFIG_FILE to set your Plex server URL and token."
echo "Then check status with: sudo systemctl status plexfs"
