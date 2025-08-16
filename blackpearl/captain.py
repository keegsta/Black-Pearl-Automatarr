#!/usr/bin/env python3
import subprocess
import time
import logging
import shutil
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
import argparse

# === CONFIGURATION ===
LOG_FILE = "/home/user/blackpearl/captains_logs/log_captain.log"
CROWS_NEST_SCRIPT = "/home/user/blackpearl/crows_nest.py"
WALK_PLANK_SCRIPT = "/home/user/blackpearl/walk_plank.py"
WASH_SCRIPT = "/home/user/blackpearl/wash.py"
CANNON_SCRIPT = "/home/user/blackpearl/cannon.py"
MEDIA_PATH = "/DATA"  # Check disk usage here
DISK_USAGE_THRESHOLD = 90  # percent
RETRY_LIMIT = 3
RETRY_DELAY = 10  # seconds

# Email settings
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
EMAIL_SENDER = "serverEmailYouCreate@gmail.com"
EMAIL_PASSWORD = "1234 1234 1234 1234"  # Use app password
EMAIL_RECEIVER = "myemail@gmail.com"

# === SETUP LOGGING ===
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# === EMAIL NOTIFICATIONS ===
def send_email(subject, body):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

# === UTILITY FUNCTIONS ===
def run_script(command_list, dry_run=False, label=""):
    attempt = 0
    while attempt < RETRY_LIMIT:
        try:
            if dry_run:
                logging.info(f"[DRY RUN] Would run: {' '.join(command_list)}")
                return 0

            logging.info(f"Running {label or 'script'}: {' '.join(command_list)}")
            result = subprocess.run(command_list, capture_output=True, text=True, check=True)
            logging.info(result.stdout)
            return 0
        except subprocess.CalledProcessError as e:
            attempt += 1
            logging.error(f"{label or 'Script'} failed on attempt {attempt}: {e.stderr}")
            time.sleep(RETRY_DELAY)
    send_email(f"[Captain] ERROR in {label or 'script'}", f"Failed after {RETRY_LIMIT} attempts:\n\n{e.stderr}")
    return 1

def get_disk_usage_percent(path):
    total, used, free = shutil.disk_usage(path)
    return used / total * 100

# === MAIN LOOP ===
def main(dry_run=False):
    last_crows_run = datetime.min
    last_walk_normal = datetime.min
    last_wash_run = datetime.min

    logging.info("🚢 Captain is now at the helm...")

    while True:
        now = datetime.now()

        # Run crows_nest.py every 30 min
        if (now - last_crows_run) >= timedelta(minutes=30):
            run_script(["python3", CROWS_NEST_SCRIPT], dry_run=dry_run, label="crows_nest.py")
            last_crows_run = now

            # Check disk usage after crows_nest
            usage = get_disk_usage_percent(MEDIA_PATH)
            logging.info(f"Disk usage: {usage:.2f}%")
            if usage >= DISK_USAGE_THRESHOLD:
                logging.warning(f"Disk usage {usage:.2f}% exceeds threshold, running walk_plank.py --all")
                run_script(["python3", WALK_PLANK_SCRIPT, "--all"], dry_run=dry_run, label="walk_plank.py --all")

        # Run walk_plank.py (normal) every 1 hour
        if (now - last_walk_normal) >= timedelta(hours=1):
            run_script(["python3", WALK_PLANK_SCRIPT], dry_run=dry_run, label="walk_plank.py")
            last_walk_normal = now

        # Run wash.py and cannon.py every 6 hours
        if (now - last_wash_run) >= timedelta(hours=6):
            wash_result = run_script(["python3", WASH_SCRIPT], dry_run=dry_run, label="wash.py")
            if wash_result == 0:
                run_script(["python3", CANNON_SCRIPT], dry_run=dry_run, label="cannon.py")
            last_wash_run = now

        time.sleep(60)  # Check every minute

# === ARGUMENTS ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Captain of the Black Pearl Media Automation")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without executing scripts")
    args = parser.parse_args()

    try:
        main(dry_run=args.dry_run)
    except Exception as e:
        logging.exception("Unexpected error in Captain")
        send_email("[Captain] Fatal Error", f"Captain.py crashed:\n\n{e}")
