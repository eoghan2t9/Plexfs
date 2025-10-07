# PlexFS

Multithreaded FUSE filesystem to mount a remote Plex server locally with SQLite caching, throttled streaming, and background refresh.

## Installation

1. Extract ZIP to server
2. Run installer:
   sudo bash install.sh
3. Edit /etc/plexfs.conf with your Plex server URL and token
4. Restart service:
   sudo systemctl restart plexfs
5. Verify mount:
   ls /media/plex
