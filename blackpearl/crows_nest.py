#!/usr/bin/env python3

import http.cookiejar
import urllib.request
import urllib.parse
import json
import os
import logging
import shutil
import smtplib
import ssl
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

# === CONFIGURATION ===
QBIT_HOST = "http://192.168.50.105:8181"
USERNAME = "admin"
PASSWORD = "qbit pass"

MANIFEST_FILE = Path("/home/user/blackpearl/captains_logs/manifest.json")
LOG_FILE = Path("/home/user/blackpearl/captains_logs/log_crows_nest.log")
DOWNLOAD_PATH = "/DATA/Downloads"
DISK_USAGE_THRESHOLD = 90  # percent
STALL_THRESHOLD_MINUTES = 30

# === EMAIL SETTINGS ===    
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
EMAIL_SENDER = "serverEmailYouCreate@gmail.com" # the email that notiifications will be coming from
EMAIL_PASSWORD = "1234 1234 1234 1234"  # gmail genreates a password that you use for bots like this script (not the email you make when you create an gmail account)
EMAIL_RECEIVER = "myemail@gmail.com"  # your personal email that will be sent the status updates, errors etc.

# === SETUP LOGGING ===
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# === COOKIE JAR ===
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cookie_jar)
)

def login():
    url = f"{QBIT_HOST}/api/v2/auth/login"
    data = urllib.parse.urlencode({
        "username": USERNAME,
        "password": PASSWORD
    }).encode()
    req = urllib.request.Request(url, data=data)
    with opener.open(req) as response:
        res = response.read().decode()
        if res != "Ok.":
            logging.error("Login failed: unexpected response")
            raise Exception("Login failed")
        logging.info("Login successful.")

def get_torrents():
    url = f"{QBIT_HOST}/api/v2/torrents/info"
    with opener.open(url) as response:
        data = json.loads(response.read().decode())
        logging.info(f"Fetched {len(data)} torrents.")
        return data

def load_manifest():
    if not MANIFEST_FILE.exists():
        return {}
    with open(MANIFEST_FILE, 'r') as f:
        data = json.load(f)
        logging.info(f"Loaded {len(data)} torrents from manifest.")
        return data

def save_manifest(data):
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    logging.info(f"Saved {len(data)} torrents to manifest.")

def minutes_since(timestamp):
    dt = datetime.now() - datetime.fromisoformat(timestamp)
    return round(dt.total_seconds() / 60)

def send_email_alert(stalled_torrents):
    if not stalled_torrents:
        return

    subject = "⚠️ qBittorrent: Stalled Torrents Detected"
    body_lines = [f"{t['name']} (stalled {t['time_stalled_minutes']} min)" for t in stalled_torrents]
    body = "\n".join(body_lines)

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        logging.info(f"Sent email alert for {len(stalled_torrents)} stalled torrents.")
    except Exception:
        logging.exception("Failed to send alert email.")

def check_disk_usage(path, threshold):
    usage = shutil.disk_usage(path)
    percent_used = (usage.used / usage.total) * 100
    logging.info(f"Disk usage at {path}: {percent_used:.2f}%")
    if percent_used > threshold:
        logging.warning(f"Disk usage exceeded threshold: {percent_used:.2f}% > {threshold}%")

def main():
    try:
        login()
        old_data = load_manifest()
        new_data = {}
        now = datetime.now().isoformat()

        for torrent in get_torrents():
            h = torrent['hash']
            name = torrent['name']
            status = torrent['state']
            eta = torrent.get('eta', -1)
            added_on = datetime.fromtimestamp(torrent['added_on']).isoformat()

            if h in old_data and status != old_data[h].get('status'):
                logging.info(f"Torrent state changed: {name} - {old_data[h].get('status')} → {status}")

            if h in old_data:
                entry = old_data[h]
                date_added = entry['date_added']
                time_stalled = int(entry.get('time_stalled_minutes', 0))
                time_seeding = int(entry.get('time_seeding_minutes', 0))

                if status == 'stalledDL':
                    time_stalled = minutes_since(entry['date_added'])
                elif status == 'uploading':
                    time_seeding = minutes_since(entry['date_added'])
            else:
                date_added = added_on
                time_stalled = 0
                time_seeding = 0
                logging.info(f"New torrent detected: {name}")

            new_data[h] = {
                'name': name,
                'status': status,
                'eta_seconds': eta,
                'date_added': date_added,
                'time_stalled_minutes': time_stalled,
                'time_seeding_minutes': time_seeding,
                'last_seen': now
            }

        # Alert logic
        stalled_alerts = [
            torrent for torrent in new_data.values()
            if torrent['status'] == 'stalledDL' and torrent['time_stalled_minutes'] >= STALL_THRESHOLD_MINUTES
        ]
        send_email_alert(stalled_alerts)
        check_disk_usage(DOWNLOAD_PATH, DISK_USAGE_THRESHOLD)

        save_manifest(new_data)
        logging.info("Update complete.")
    except Exception:
        logging.exception("Unexpected error occurred.")

if __name__ == "__main__":
    main()
