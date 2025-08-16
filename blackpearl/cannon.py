#!/usr/bin/env python3
import os
import shutil
import subprocess
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
import argparse
import time
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3

def parse_args():
    parser = argparse.ArgumentParser(description="Move media files to remote Plex storage.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without making changes")
    return parser.parse_args()

def format_size(bytes_size):
    """Convert bytes to a human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} PB"

INCOMPLETE_EXTENSIONS = [".part", ".!qB", ".tmp", ".unfinished"]
MODIFIED_WITHIN_MINUTES = 0

# Email config
SEND_EMAIL_IN_DRY_RUN = True
EMAIL_ENABLED = True
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "serverEmailYouCreate@gmail.com"
SMTP_PASSWORD = "1234 1234 1234 1234"
EMAIL_FROM = "serverEmailYouCreate@gmail.com" 
EMAIL_TO = "myemail@gmail.com" #your personal email

# Configuration
LOCAL_BASE = Path("/DATA/Media")
REMOTE_MOUNT = Path("/mnt/myremote")
REMOTE_SHARE = "//path/PlexMediaServer"
CREDENTIALS_FILE = "/home/user/blackpearl/remote_credentials"
MEDIA_FOLDERS = ["Books", "Movies", "Music", "TV Shows"]
LOG_FILE = "/home/user/blackpearl/captains_logs/log_cannon.log"

# Setup logging
logger = logging.getLogger("MediaMover")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

import atexit
from pathlib import Path

# TV episode & sidecar extensions
EPISODE_EXTS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".flv"}
SIDECAR_EXTS = {".srt", ".sub", ".idx", ".ass", ".ssa", ".nfo"}

def send_error_email(subject, body):
    if not EMAIL_ENABLED:
        return

    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info("Error email sent.")
    except Exception as e:
        logger.error(f"Failed to send error email: {e}")

def send_success_email(count, total_size, moved_files, dry_run=False, subject_label="Files"):
    if not EMAIL_ENABLED:
        return

    subject = f"Successfully Transferred {count} {subject_label} ({format_size(total_size)}) to Remote"
    if dry_run:
        subject = "[DRY RUN] " + subject

    dry_run_note = "<p><strong>NOTE:</strong> This was a dry run. No actual files were moved.</p>" if dry_run else ""

    body_html = f"""
    <html>
    <body>
        <h2>MediaMover Summary</h2>
        {dry_run_note}
        <p><strong>{subject_label} Moved:</strong> {count}</p>
        <p><strong>Total Size:</strong> {format_size(total_size)}</p>
        <p><strong>Destination:</strong> Remote</p>
        <h3>Moved Items:</h3>
        <ul>
            {''.join(f"<li>{f}</li>" for f in moved_files)}
        </ul>
    </body>
    </html>
    """

    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.set_content("This is an HTML email. Please view in HTML-compatible email client.")
        msg.add_alternative(body_html, subtype="html")

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        print("✅ Success email sent.")
        logger.info("Success email sent.")
    except Exception as e:
        print(f"❌ Failed to send success email: {e}")
        logger.error(f"Failed to send success email: {e}")

def mount_remote():
    """Ensure the remote SMB share is mounted and usable."""
    try:
        # Make sure mount point exists
        REMOTE_MOUNT.mkdir(parents=True, exist_ok=True)

        def is_mount_usable():
            test_path = REMOTE_MOUNT / "Books"
            try:
                return test_path.exists()
            except OSError:
                return False

        # If already mounted but not usable, force unmount
        with open("/proc/mounts", "r") as mounts:
            is_mounted = any(str(REMOTE_MOUNT) in line for line in mounts)

        if is_mounted and not is_mount_usable():
            logger.warning(f"{REMOTE_MOUNT} is mounted but unusable. Forcing unmount...")
            subprocess.run(["umount", "-f", str(REMOTE_MOUNT)], check=False)

        # Retry mount if needed
        if not is_mount_usable():
            logger.info(f"Mounting {REMOTE_SHARE} to {REMOTE_MOUNT}")
            subprocess.run([
                "mount", "-t", "cifs", REMOTE_SHARE, str(REMOTE_MOUNT),
                "-o", f"credentials={CREDENTIALS_FILE},iocharset=utf8,vers=3.0"
            ], check=True)

            # Re-verify
            if not is_mount_usable():
                raise OSError(f"Mount succeeded but {REMOTE_MOUNT}/Books is still inaccessible.")

            logger.info("Mount successful and verified.")
        else:
            logger.info(f"{REMOTE_MOUNT} is already mounted and usable.")

    except Exception as e:
        logger.error(f"Failed to mount remote share: {e}")
        raise

def resolve_filename_conflict(dest_path):
    """Rename file if a conflict exists in destination directory."""
    if not dest_path.exists():
        return dest_path

    counter = 1
    new_path = dest_path
    while new_path.exists():
        new_name = f"{dest_path.stem}_{counter}{dest_path.suffix}"
        new_path = dest_path.with_name(new_name)
        counter += 1
    return new_path

def move_files(dry_run):
    total_files_moved = 0           # overall count (episodes + other items)
    total_bytes_moved = 0
    moved_files_list = []
    tv_episodes_moved = 0
    non_tv_items_moved = 0
    start_time = datetime.now()

    def _dir_size(path: Path) -> int:
        total = 0
        for root, _, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
        return total

    def _count_episodes(path: Path) -> int:
        count = 0
        for f in path.rglob("*"):
            if f.is_file() and f.suffix.lower() in EPISODE_EXTS:
                count += 1
        return count

    for folder in MEDIA_FOLDERS:
        local_path = LOCAL_BASE / folder
        remote_path = REMOTE_MOUNT / folder

        if not remote_path.exists():
            logger.info(f"Creating remote folder: {remote_path}")
            if not dry_run:
                remote_path.mkdir(parents=True, exist_ok=True)

        # 📦 TV Shows: move by show/season, avoid nested show folders
        if folder == "TV Shows":
            for show_folder in local_path.iterdir():
                if not show_folder.is_dir():
                    continue

                dest_show = remote_path / show_folder.name
                source_seasons = [p for p in show_folder.iterdir() if p.is_dir()]  # Season folders

                if dry_run:
                    # simulate by summing episode counts and bytes
                    show_bytes = _dir_size(show_folder)
                    episode_count = _count_episodes(show_folder)
                    print(f"[DRY RUN] Would move show: {show_folder} → {dest_show} "
                          f"({episode_count} episodes, {format_size(show_bytes)})")
                    logger.info(f"[DRY RUN] Would move show: {show_folder} → {dest_show} "
                                f"({episode_count} episodes, {format_size(show_bytes)})")
                    total_files_moved += episode_count
                    tv_episodes_moved += episode_count
                    total_bytes_moved += show_bytes
                    moved_files_list.append(f"{show_folder} → {dest_show} "
                                            f"({episode_count} episodes, {format_size(show_bytes)})")
                else:
                    try:
                        # If destination show doesn't exist, move whole show then verify size
                        if not dest_show.exists():
                            show_bytes_before = _dir_size(show_folder)
                            episode_count = _count_episodes(show_folder)

                            print(f"Starting show: {show_folder.name} "
                                  f"({episode_count} episodes, {format_size(show_bytes_before)})")
                            logger.info(f"Starting show: {show_folder.name} "
                                        f"({episode_count} episodes, {format_size(show_bytes_before)})")

                            move_ok = False
                            for attempt in range(1, RETRY_ATTEMPTS + 1):
                                try:
                                    shutil.move(str(show_folder), str(dest_show))
                                    # verify folder size after move
                                    if dest_show.exists() and _dir_size(dest_show) == show_bytes_before:
                                        move_ok = True
                                        break
                                    else:
                                        raise Exception("Show folder size mismatch after move.")
                                except Exception as err:
                                    if attempt < RETRY_ATTEMPTS:
                                        print(f"⚠️  Retry {attempt}/{RETRY_ATTEMPTS} failed for {show_folder}. "
                                              f"Retrying in {RETRY_DELAY_SECONDS}s...")
                                        logger.warning(f"Retry {attempt}/{RETRY_ATTEMPTS} failed for {show_folder}: {err}")
                                        time.sleep(RETRY_DELAY_SECONDS)
                                    else:
                                        raise

                            if move_ok:
                                print(f"Finished show: {show_folder.name}")
                                logger.info(f"Finished show: {show_folder.name}")
                                total_files_moved += episode_count
                                tv_episodes_moved += episode_count
                                total_bytes_moved += show_bytes_before
                                moved_files_list.append(f"{show_folder} → {dest_show} "
                                                        f"({episode_count} episodes, {format_size(show_bytes_before)})")
                            else:
                                print(f"❌ Verification failed for show {show_folder}")
                                logger.error(f"Verification failed for show {show_folder}")
                        else:
                            # Destination show exists: move seasons individually (no nested show folder)
                            for season_dir in source_seasons:
                                dest_season = dest_show / season_dir.name
                                season_bytes_before = _dir_size(season_dir)
                                season_episodes = _count_episodes(season_dir)

                                print(f"Starting season: {show_folder.name}/{season_dir.name} "
                                      f"({season_episodes} episodes, {format_size(season_bytes_before)})")
                                logger.info(f"Starting season: {show_folder.name}/{season_dir.name} "
                                            f"({season_episodes} episodes, {format_size(season_bytes_before)})")

                                if not dest_season.exists():
                                    # move the whole season folder
                                    move_ok = False
                                    for attempt in range(1, RETRY_ATTEMPTS + 1):
                                        try:
                                            shutil.move(str(season_dir), str(dest_season))
                                            if dest_season.exists() and _dir_size(dest_season) == season_bytes_before:
                                                move_ok = True
                                                break
                                            else:
                                                raise Exception("Season folder size mismatch after move.")
                                        except Exception as err:
                                            if attempt < RETRY_ATTEMPTS:
                                                print(f"⚠️  Retry {attempt}/{RETRY_ATTEMPTS} failed for {season_dir}. "
                                                      f"Retrying in {RETRY_DELAY_SECONDS}s...")
                                                logger.warning(f"Retry {attempt}/{RETRY_ATTEMPTS} failed for {season_dir}: {err}")
                                                time.sleep(RETRY_DELAY_SECONDS)
                                            else:
                                                raise
                                    if move_ok:
                                        print(f"Finished season: {season_dir.name}")
                                        logger.info(f"Finished season: {season_dir.name}")
                                        total_files_moved += season_episodes
                                        tv_episodes_moved += season_episodes
                                        total_bytes_moved += season_bytes_before
                                        moved_files_list.append(f"{season_dir} → {dest_season} "
                                                                f"({season_episodes} episodes, {format_size(season_bytes_before)})")
                                else:
                                    # destination season already exists -> merge files
                                    for f in season_dir.rglob("*"):
                                        if not f.is_file():
                                            continue
                                        file_size = f.stat().st_size
                                        rel_path = f.relative_to(season_dir)
                                        dest_file = dest_season / rel_path
                                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                                        safe_dest = resolve_filename_conflict(dest_file)

                                        move_successful = False
                                        for attempt in range(1, RETRY_ATTEMPTS + 1):
                                            try:
                                                shutil.move(str(f), str(safe_dest))
                                                if safe_dest.exists() and safe_dest.stat().st_size == file_size:
                                                    move_successful = True
                                                    break
                                                else:
                                                    raise Exception("Moved file failed verification.")
                                            except Exception as err:
                                                if attempt < RETRY_ATTEMPTS:
                                                    print(f"⚠️  Retry {attempt}/{RETRY_ATTEMPTS} failed for {f}. "
                                                          f"Retrying in {RETRY_DELAY_SECONDS}s...")
                                                    logger.warning(f"Retry {attempt}/{RETRY_ATTEMPTS} failed for {f}: {err}")
                                                    time.sleep(RETRY_DELAY_SECONDS)
                                                else:
                                                    raise

                                        if move_successful:
                                            total_bytes_moved += file_size
                                            if f.suffix.lower() in EPISODE_EXTS:
                                                total_files_moved += 1
                                                tv_episodes_moved += 1
                                            moved_files_list.append(f"{f} → {safe_dest}")

                                    # remove empty source season folder
                                    try:
                                        if not any(season_dir.rglob("*")):
                                            season_dir.rmdir()
                                    except Exception as e:
                                        logger.warning(f"Could not remove empty season dir {season_dir}: {e}")

                            # after processing seasons, remove now-empty show folder
                            try:
                                if not any(show_folder.rglob("*")):
                                    show_folder.rmdir()
                            except Exception as e:
                                logger.warning(f"Could not remove empty show dir {show_folder}: {e}")

                    except Exception as e:
                        print(f"❌ Error moving show {show_folder}: {e}")
                        logger.error(f"Failed to move show {show_folder}: {e}")
            continue  # done with TV Shows

        # 📁 Books, Movies, Music: per-file logic + verification
        for item in local_path.iterdir():
            if item.is_dir():
                files = list(item.glob("**/*"))
                now = datetime.now()
                file_files = []
                verified_files = []

                for f in files:
                    if not f.is_file():
                        continue
                    if f.suffix in INCOMPLETE_EXTENSIONS:
                        logger.info(f"Skipping incomplete file: {f}")
                        continue
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if (now - mtime) < timedelta(minutes=MODIFIED_WITHIN_MINUTES):
                        logger.info(f"Skipping recently modified file: {f}")
                        continue
                    file_files.append(f)

                for f in file_files:
                    dest = remote_path / f.name
                    safe_dest = resolve_filename_conflict(dest)

                    if dry_run:
                        try:
                            file_size = f.stat().st_size
                        except OSError:
                            file_size = 0
                        print(f"[DRY RUN] Would move: {f} → {safe_dest} ({format_size(file_size)})")
                        logger.info(f"[DRY RUN] Would move: {f} → {safe_dest} ({format_size(file_size)})")
                        total_files_moved += 1
                        non_tv_items_moved += 1
                        total_bytes_moved += file_size
                        moved_files_list.append(f"{f} → {safe_dest} ({format_size(file_size)})")
                        verified_files.append(f)
                    else:
                        file_size = f.stat().st_size
                        move_successful = False
                        try:
                            print(f"Starting: {f.name} ({format_size(file_size)})")
                            logger.info(f"Starting: {f.name} ({format_size(file_size)})")

                            for attempt in range(1, RETRY_ATTEMPTS + 1):
                                try:
                                    shutil.move(str(f), str(safe_dest))
                                    if safe_dest.exists() and safe_dest.stat().st_size == file_size:
                                        move_successful = True
                                        break
                                    else:
                                        raise Exception("Moved file failed verification.")
                                except Exception as move_err:
                                    if attempt < RETRY_ATTEMPTS:
                                        print(f"⚠️  Retry {attempt}/{RETRY_ATTEMPTS} failed for {f}. "
                                              f"Retrying in {RETRY_DELAY_SECONDS}s...")
                                        logger.warning(f"Retry {attempt}/{RETRY_ATTEMPTS} failed for {f}: {move_err}")
                                        time.sleep(RETRY_DELAY_SECONDS)
                                    else:
                                        raise

                            if move_successful:
                                print(f"Finished: {f.name}")
                                logger.info(f"Finished: {f.name}")
                                moved_files_list.append(f"{f} → {safe_dest} ({format_size(file_size)})")
                                total_files_moved += 1
                                non_tv_items_moved += 1
                                total_bytes_moved += file_size
                                verified_files.append(f)
                            else:
                                print(f"❌ Verification failed after moving {f}")
                                logger.error(f"Verification failed after moving {f}")
                        except Exception as e:
                            print(f"❌ Error moving {f}: {e}")
                            logger.error(f"Failed to move {f}: {e}")

                if not dry_run and verified_files:
                    try:
                        shutil.rmtree(item)
                        print(f"Deleted folder: {item}")
                        logger.info(f"Deleted folder: {item}")
                    except Exception as e:
                        print(f"❌ Error deleting {item}: {e}")
                        logger.error(f"Failed to delete {item}: {e}")

    elapsed = datetime.now() - start_time
    # smart label for subject
    if tv_episodes_moved > 0 and non_tv_items_moved == 0:
        subject_label = "Episodes"
    elif tv_episodes_moved > 0 and non_tv_items_moved > 0:
        subject_label = "Items"
    else:
        subject_label = "Files"

    summary = (
        f"MediaMover Summary:\n"
        f"{subject_label} moved: {total_files_moved}\n"
        f"Total size: {format_size(total_bytes_moved)}\n"
        f"Elapsed time: {elapsed}\n\n"
    )

    if moved_files_list:
        summary += "Moved items:\n" + "\n".join(moved_files_list)

    print(summary)
    logger.info(summary)

    if (not dry_run and total_files_moved > 0) or (dry_run and SEND_EMAIL_IN_DRY_RUN):
        send_success_email(total_files_moved, total_bytes_moved, moved_files_list, dry_run=dry_run, subject_label=subject_label)

def main():
    args = parse_args()
    dry_run = args.dry_run

    logger.info("=== Starting MediaMover ===")
    if dry_run:
        logger.info("Running in DRY RUN mode (no changes will be made).")

    try:
        mount_remote()
        move_files(dry_run)
    except Exception as e:
        logger.exception(f"Unhandled error: {e}")
        send_error_email(
            subject="MediaMover Error",
            body=f"An error occurred during execution:\n\n{str(e)}"
        )
    print("✅ MediaMover run completed.")
    logger.info("=== Finished MediaMover ===")

if __name__ == "__main__":
    main()