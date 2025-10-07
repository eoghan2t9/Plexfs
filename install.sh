#!/bin/bash
set -e
USER_NAME=$(whoami)
MOUNT_POINT="/media/plex"
LOG_PATH="/var/log/plexfs.log"
CACHE_DIR="/var/cache/plexfs"
PLEXFS_BIN="/usr/local/bin/plexfs.py"
CONFIG_FILE="/etc/plexfs.conf"

sudo apt update
sudo apt install -y python3-pip fuse python3-fuse
sudo pip3 install requests plexapi fusepy

sudo mkdir -p "$MOUNT_POINT" "$CACHE_DIR" /var/log
sudo touch "$LOG_PATH"
sudo chown -R "$USER_NAME":"$USER_NAME" "$MOUNT_POINT" "$LOG_PATH" "$CACHE_DIR"
sudo chmod 755 "$MOUNT_POINT" "$CACHE_DIR"
sudo chmod 644 "$LOG_PATH"

sudo cp plexfs.py "$PLEXFS_BIN"
sudo chmod +x "$PLEXFS_BIN"

sudo cp plexfs.conf.template "$CONFIG_FILE"

sudo tee /etc/systemd/system/plexfs.service > /dev/null <<EOF
[Unit]
Description=Mount Plex Server via FUSE
After=network.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
ExecStart=/usr/local/bin/plexfs.py
Restart=on-failure
RestartSec=5
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable plexfs
sudo systemctl start plexfs
sudo systemctl status plexfs

echo "PlexFS installed! Edit $CONFIG_FILE with your Plex server URL and token."
