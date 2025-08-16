#!/usr/bin/env python3

import os
import re
import logging
from pathlib import Path
from datetime import datetime

MEDIA_ROOT = Path("/DATA/Media")    # where the torrents are downloaded
CATEGORIES = ["Books", "Movies", "Music", "TV Shows"]
LOG_FILE = Path("/home/user/blackpearl/captains_logs/log_wash.log")

REMOVE_PATTERNS = [
    r'\b(480p|720p|1080p|2160p|4K|8K|BDRemux|Remux|BluRay|BRRip|WEBRip|WEB-DL|HDRip|DVDRip|HDTV|NF|AMZN|HMAX|MAX|DSNP|AVC|HEVC|x264|x265|H\.264|H\.265)\b',
    r'\b(DTS(?:-HD)?|AAC(?:5\.1)?|AC3|FLAC|MP3|EAC3|TrueHD|Atmos(?:\d+\.\d+)?|DDP|DD5\.1|5\.1|7\.1)\b',
    r'\b(ENG|EN|DEU|GER|FRE|ITA|SPA|JPN|KOR|RUS|HIN|MULTI|DUALAUDIO)\b',
    r'\b(YTS|RARBG|EVO|FGT|CRF|PSA|CM8|LOL|BATV|ROVERS|NTb|TBS|SVA|DIMENSION|DRONES|RuTracker|TGx|GalaxyRG)\b',
    r'\b(Extended|Remastered|Proper|REPACK|LIMITED|Unrated|HDR|HC|Dubbed|Subbed|Subs|Complete|Retail|Internal|Theatrical|Regraded|Sample)\b',
    r'[\[\]{}()_.\-]+',
    r'\s{2,}',
]

TV_EPISODE_PATTERN = re.compile(r'(S\d{1,2}E\d{1,2})', re.IGNORECASE)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def clean_filename(filename, folder_name, media_type):
    name, ext = os.path.splitext(filename)

    if media_type == "TV Shows":
        # Match SxxExx
        episode_match = TV_EPISODE_PATTERN.search(name)
        episode = episode_match.group(0).upper() if episode_match else ""

        # Remove known junk patterns
        clean_name = name
        for pattern in REMOVE_PATTERNS:
            clean_name = re.sub(pattern, ' ', clean_name, flags=re.IGNORECASE)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()

        # Extract show name from cleaned name (before episode)
        show_name = "Unknown Show"
        if episode:
            parts = clean_name.split(episode, maxsplit=1)
            show_name = parts[0].strip(" -")

            # Remove any embedded 4-digit year from show name
            show_name = re.sub(r'\b(19|20)\d{2}\b', '', show_name).strip()
            show_name = re.sub(r'\s+', ' ', show_name).strip().title()

        # Build final filename without episode title
        if episode:
            final_name = f"{show_name} - {episode}{ext.lower()}"
        else:
            final_name = f"{clean_name.title()}{ext.lower()}"

        return final_name

    else:
        # Movies, Music, Books
        base_title = re.sub(r'[()\[\]{}]', '', folder_name)
        base_title = re.sub(r'\s{2,}', ' ', base_title).strip()
        base_title = base_title.title()
        return f"{base_title}{ext.lower()}"

def clean_media_files(dry_run=False):
    for category in CATEGORIES:
        folder_path = MEDIA_ROOT / category
        if not folder_path.exists():
            print(f"⚠️ Skipping missing folder: {folder_path}")
            continue

        for root, _, files in os.walk(folder_path):
            folder_name = Path(root).name
            file_paths = [Path(root) / f for f in files]

            if not file_paths:
                continue

            renamed = skipped = errors = 0
            print(f"\n📁 {folder_name}")

            for file_path in file_paths:
                file = file_path.name
                new_name = clean_filename(file, folder_name, category)

                if not new_name:
                    continue

                new_path = Path(root) / new_name

                if new_path.exists():
                    print(f"⚠️ Skipped (exists): {new_name}")
                    skipped += 1
                    continue

                try:
                    if dry_run:
                        print(f"[DRY-RUN] Would rename: {file_path.name} → {new_name}")
                    else:
                        file_path.rename(new_path)
                        logging.info(f"RENAME | {file_path} | {new_path}")
                        print(f"✅ Renamed: {file_path.name} → {new_name}")
                    renamed += 1
                except Exception as e:
                    print(f"❌ Error renaming {file_path.name}: {e}")
                    errors += 1

            print(f"📊 Summary for {folder_name}:")
            print(f"  Found:   {len(file_paths)}")
            print(f"  Renamed: {renamed}")
            print(f"  Skipped: {skipped}")
            print(f"  Errors:  {errors}")

def undo_last_changes():
    if not LOG_FILE.exists():
        print("Log file not found. Cannot undo.")
        return

    with open(LOG_FILE, 'r') as f:
        lines = f.readlines()

    undone = 0

    for line in reversed(lines):
        if "RENAME" not in line:
            continue
        try:
            _, old_path, new_path = line.strip().split(" | ")
            old_path = Path(old_path)
            new_path = Path(new_path)
            if new_path.exists() and not old_path.exists():
                new_path.rename(old_path)
                print(f"Undone: {new_path.name} → {old_path.name}")
                logging.info(f"UNDO | {new_path} | {old_path}")
                undone += 1
        except Exception as e:
            print(f"Failed to undo rename: {e}")

    if undone == 0:
        print("No renames were undone.")
    else:
        print(f"Undo complete. {undone} files restored.")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Media File Cleaner")
    parser.add_argument("--undo", action="store_true", help="Undo the last renames from the log")
    parser.add_argument("--dry-run", action="store_true", help="Preview renames without changing files")

    args = parser.parse_args()

    if args.undo:
        undo_last_changes()
    else:
        clean_media_files(dry_run=args.dry_run)
