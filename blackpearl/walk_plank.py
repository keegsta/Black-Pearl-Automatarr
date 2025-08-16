#!/usr/bin/env python3

import requests
import argparse
import logging
from pathlib import Path

# ==== CONFIGURATION ====
QBITTORRENT_API = "http://192.168.50.105:8181"  # Update if needed
QBIT_USERNAME = "admin"
QBIT_PASSWORD = "qbittorrent password"

CROWS_API_URL = "http://192.168.50.105:5050/status"
DEFAULT_THRESHOLD_HOURS = 168   # hours too keep before deleting

LOG_PATH = Path.home() / "/home/user/blackpearl/captains_logs/log_walk_plank.log"
# ========================

# Setup logging
logging.basicConfig(
    filename=LOG_PATH,
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

SESSION = requests.Session()

def login():
    try:
        resp = SESSION.post(f"{QBITTORRENT_API}/api/v2/auth/login", data={
            "username": QBIT_USERNAME,
            "password": QBIT_PASSWORD
        })
        if resp.text != "Ok.":
            raise Exception("Login failed")
    except Exception as e:
        logging.error(f"Failed to log in: {e}")
        raise

def get_torrents():
    try:
        resp = SESSION.get(f"{QBITTORRENT_API}/api/v2/torrents/info")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logging.error(f"Failed to fetch torrents: {e}")
        return []

def delete_torrent(hash_, name, dry_run, delete_files=True):
    try:
        if dry_run:
            logging.info(f"[DRY RUN] Would delete torrent: {name} ({hash_})")
            return
        SESSION.post(f"{QBITTORRENT_API}/api/v2/torrents/delete", data={
            "hashes": hash_,
            "deleteFiles": str(delete_files).lower()
        })
        logging.info(f"Deleted torrent: {name} ({hash_})")
    except Exception as e:
        logging.error(f"Error deleting torrent {name} ({hash_}): {e}")

def fetch_crows_data():
    try:
        resp = requests.get(CROWS_API_URL)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logging.error(f"Failed to fetch Crows Nest data: {e}")
        return {}

def should_delete_based_on_crows(torrent, crows_data, threshold_minutes):
    info = crows_data.get(torrent["hash"])
    if not info:
        return False
    seeding_minutes = info.get("time_seeding_minutes", 0)
    stalled_minutes = info.get("time_stalled_minutes", 0)
    return (seeding_minutes > threshold_minutes) or (stalled_minutes > threshold_minutes)

def main():
    parser = argparse.ArgumentParser(description="Delete seeding torrents from qBittorrent.")
    parser.add_argument('--all', action='store_true', help="Delete all seeding torrents.")
    parser.add_argument('--dry-run', action='store_true', help="Only simulate deletions.")
    parser.add_argument('--threshold-hours', type=int, default=DEFAULT_THRESHOLD_HOURS,
                        help="Threshold in hours before deleting seeding/stalled torrents.")
    args = parser.parse_args()

    threshold_minutes = args.threshold_hours * 60

    try:
        login()
        torrents = get_torrents()

        if args.all:
            to_delete = [t for t in torrents if t["state"] == "uploading"]
        else:
            crows_data = fetch_crows_data()
            to_delete = [
                t for t in torrents
                if t["state"] == "uploading" and should_delete_based_on_crows(t, crows_data, threshold_minutes)
            ]

        for torrent in to_delete:
            delete_torrent(torrent["hash"], torrent["name"], dry_run=args.dry_run)

        if not to_delete:
            logging.info("No torrents matched the criteria for deletion.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
