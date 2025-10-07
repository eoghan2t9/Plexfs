#!/usr/bin/env python3
import os, sys, time, sqlite3, threading
from plexapi.server import PlexServer
from fuse import FUSE, Operations

CONFIG_FILE = '/etc/plexfs.conf'

# Load configuration
import configparser
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

BASE_URL = config.get('plex', 'base_url')
TOKEN = config.get('plex', 'token')
MOUNT_POINT = config.get('plex', 'mount_point')
CACHE_DB = config.get('plex', 'cache_db')
STREAM_LIMIT = config.getint('plex', 'stream_limit_bytes_per_sec', fallback=0)
CHUNK_SIZE = config.getint('plex', 'chunk_size_bytes', fallback=524288)

# Connect to Plex server
plex = PlexServer(BASE_URL, TOKEN)

# SQLite cache setup
conn = sqlite3.connect(CACHE_DB, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS library_items (
    key TEXT PRIMARY KEY,
    title TEXT,
    path TEXT,
    library TEXT
)''')
conn.commit()

# Background refresh thread
def refresh_cache():
    while True:
        for section in plex.library.sections():
            library_name = section.title
            for item in section.all():
                try:
                    # Movies
                    if item.type == 'movie' and item.media and item.media[0].parts:
                        path = item.media[0].parts[0].file
                        c.execute('INSERT OR REPLACE INTO library_items VALUES (?,?,?,?)',
                                  (item.key, item.title, path, library_name))
                    # Shows → iterate episodes
                    elif item.type == 'show':
                        for episode in item.episodes():
                            if episode.media and episode.media[0].parts:
                                path = episode.media[0].parts[0].file
                                c.execute('INSERT OR REPLACE INTO library_items VALUES (?,?,?,?)',
                                          (episode.key, episode.title, path, library_name))
                except Exception as e:
                    print(f"[WARN] Failed to cache {item.title}: {e}")
        conn.commit()
        time.sleep(config.getint('plex', 'refresh_interval', fallback=3600))

threading.Thread(target=refresh_cache, daemon=True).start()

# FUSE filesystem with library-based virtual folders
class PlexFS(Operations):
    def __init__(self):
        self.path_map = {}
        c.execute('SELECT path, library, title FROM library_items')
        for path, library, title in c.fetchall():
            # Only include common media files
            if os.path.splitext(path)[1].lower() in ['.mp4', '.mkv', '.avi', '.mov', '.flv']:
                virtual_path = os.path.join("/", library, os.path.basename(path))
                self.path_map[virtual_path] = path

    def readdir(self, path, fh):
        dirs = set()
        files = []
        for vpath in self.path_map.keys():
            parent = os.path.dirname(vpath)
            if parent == path:
                files.append(os.path.basename(vpath))
            elif os.path.dirname(parent) == path:
                dirs.add(os.path.basename(parent))
        return ['.', '..'] + list(dirs) + files

    def open(self, path, flags):
        real_path = self.path_map.get(path)
        if not real_path:
            raise FileNotFoundError(path)
        return os.open(real_path, flags)

    def read(self, path, size, offset, fh):
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, size)

    def release(self, path, fh):
        os.close(fh)

if __name__ == '__main__':
    FUSE(PlexFS(), MOUNT_POINT, nothreads=False, foreground=True)
    
