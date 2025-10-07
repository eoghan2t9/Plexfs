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

plex = PlexServer(BASE_URL, TOKEN)

# SQLite cache setup
conn = sqlite3.connect(CACHE_DB, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS library_items (key TEXT PRIMARY KEY, title TEXT, path TEXT)''')
conn.commit()

# Background refresh thread
def refresh_cache():
    while True:
        for section in plex.library.sections():
            for item in section.all():
                if item.media and item.media[0].parts:
                    path = item.media[0].parts[0].file
                    c.execute('INSERT OR REPLACE INTO library_items VALUES (?,?,?)', (item.key, item.title, path))
        conn.commit()
        time.sleep(config.getint('plex', 'refresh_interval', fallback=3600))

threading.Thread(target=refresh_cache, daemon=True).start()

# FUSE filesystem
class PlexFS(Operations):
    def __init__(self):
        self.files = {}
        c.execute('SELECT path FROM library_items')
        for row in c.fetchall():
            self.files[row[0]] = True

    def readdir(self, path, fh):
        return ['.', '..'] + [os.path.basename(p) for p in self.files if os.path.dirname(p) == path]

    def open(self, path, flags):
        return os.open(path, flags)

    def read(self, path, size, offset, fh):
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, min(size, CHUNK_SIZE))

    def release(self, path, fh):
        os.close(fh)

if __name__ == '__main__':
    FUSE(PlexFS(), MOUNT_POINT, nothreads=False, foreground=True)
