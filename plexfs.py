#!/usr/bin/env python3
import os
import sys
import time
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from fuse import FUSE, Operations
from plexapi.server import PlexServer
import configparser

# ───────────────────────────────────────────────
# Configuration
# ───────────────────────────────────────────────
CONFIG_FILE = '/etc/plexfs.conf'
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

BASE_URL = config.get('plex', 'base_url')
TOKEN = config.get('plex', 'token')
MOUNT_POINT = config.get('plex', 'mount_point', fallback='/media/plex')
CACHE_DB = config.get('plex', 'cache_db', fallback='/var/lib/plexfs/cache.db')
REFRESH_INTERVAL = config.getint('plex', 'refresh_interval', fallback=3600)
MAX_THREADS = config.getint('plex', 'max_threads', fallback=8)

# ───────────────────────────────────────────────
# Plex + SQLite setup
# ───────────────────────────────────────────────
plex = PlexServer(BASE_URL, TOKEN)

os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
conn = sqlite3.connect(CACHE_DB, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS library_items (
    key TEXT PRIMARY KEY,
    title TEXT,
    path TEXT,
    library TEXT
)
""")
conn.commit()
lock = threading.Lock()

# ───────────────────────────────────────────────
# Helper: cache one Plex item
# ───────────────────────────────────────────────
def cache_item(item, library_name):
    try:
        if item.type == 'movie':
            for media in item.media:
                for part in media.parts:
                    path = part.file
                    with lock:
                        cur.execute('INSERT OR REPLACE INTO library_items VALUES (?,?,?,?)',
                                    (item.key, item.title, path, library_name))

        elif item.type == 'show':
            for ep in item.episodes():
                for media in ep.media:
                    for part in media.parts:
                        path = part.file
                        with lock:
                            cur.execute('INSERT OR REPLACE INTO library_items VALUES (?,?,?,?)',
                                        (ep.key, ep.title, path, library_name))
    except Exception as e:
        print(f"[WARN] Failed to cache {item.title}: {e}")

# ───────────────────────────────────────────────
# Fast background cache refresh
# ───────────────────────────────────────────────
def refresh_cache():
    while True:
        print("[INFO] Starting Plex library scan...")
        for section in plex.library.sections():
            library_name = section.title
            print(f"[SCAN] {library_name}")
            try:
                # Faster: search returns partial objects (less metadata overhead)
                items = section.search(libtype=section.type)
                with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                    for item in items:
                        executor.submit(cache_item, item, library_name)
            except Exception as e:
                print(f"[ERROR] Failed to scan {library_name}: {e}")

        conn.commit()
        print("[INFO] Plex library cache refreshed.")
        time.sleep(REFRESH_INTERVAL)

# ───────────────────────────────────────────────
# FUSE Filesystem
# ───────────────────────────────────────────────
class PlexFS(Operations):
    def __init__(self):
        self._load_path_map()

    def _load_path_map(self):
        """Rebuild path map from cache."""
        self.path_map = {}
        cur.execute('SELECT path, library, title FROM library_items')
        for path, library, title in cur.fetchall():
            if not path:
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv']:
                virtual_path = os.path.join("/", library, os.path.basename(path))
                self.path_map[virtual_path] = path
        print(f"[INFO] {len(self.path_map)} files indexed in FUSE view")

    def readdir(self, path, fh):
        dirs = set()
        files = []
        for vpath in self.path_map.keys():
            parent = os.path.dirname(vpath)
            if parent == path:
                files.append(os.path.basename(vpath))
            elif os.path.dirname(parent) == path:
                dirs.add(os.path.basename(parent))
        return ['.', '..'] + sorted(list(dirs)) + sorted(files)

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

# ───────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────
if __name__ == '__main__':
    threading.Thread(target=refresh_cache, daemon=True).start()
    FUSE(PlexFS(), MOUNT_POINT, nothreads=False, foreground=True)
