#!/usr/bin/env python3
"""
Bandcamp Download 2.0 scheduler.

Runs `bandcamp_download.py --sync -y` once a day. This is the Docker container's
main process.

Settings (environment variables):
  SYNC_TIME     time of day to run, 24h HH:MM in the container's TZ (default 04:00)
  TZ            time zone, e.g. America/New_York (default UTC)
  RUN_ON_START  "true" to also run a sync as soon as the container starts
  SYNC_ARGS     extra arguments for the sync, e.g. "--format mp3-320"
  NOTIFY_URL    ntfy topic URL for push notifications, e.g. https://ntfy.sh/some-long-random-name
                (sent when the login cookie expires or a sync fails; bandcamp_download.py
                itself sends one for each show it downloads)
  NOTIFY_DOWNLOADS  "false" to skip the per-show "new show" notifications
  NOTIFY_TOKEN  access token, only if your ntfy topic is protected

Test notifications with:  python scheduler.py --test-notify
"""

import collections
import datetime
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bandcamp_download.py")


def log(msg):
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def parse_time(s):
    try:
        h, m = (int(x) for x in s.strip().split(":"))
        return datetime.time(h, m)
    except ValueError:
        sys.exit(f"SYNC_TIME must look like 04:00, got {s!r}")


def next_run(at):
    now = datetime.datetime.now()
    run = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return run if run > now else run + datetime.timedelta(days=1)


EXIT_NOT_LOGGED_IN = 3  # matches bandcamp_download.py


def notify(title, message, priority="default", tags=""):
    """Send a push notification via ntfy (NOTIFY_URL, e.g. https://ntfy.sh/your-topic).
    Does nothing if NOTIFY_URL isn't set; never lets a notification problem stop the sync."""
    url = os.environ.get("NOTIFY_URL", "").strip()
    if not url:
        return False
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags
    token = os.environ.get("NOTIFY_TOKEN", "").strip()  # only for protected ntfy topics
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, data=message.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        log(f"Sent notification: {title}")
        return True
    except Exception as e:
        log(f"Couldn't send notification ({e})")
        return False


def run_sync():
    cmd = [sys.executable, "-u", SCRIPT, "--sync", "--yes"] + shlex.split(os.environ.get("SYNC_ARGS", ""))
    log("Starting sync: " + " ".join(shlex.quote(c) for c in cmd[2:]))
    start = time.monotonic()
    # Pass the output through to the log, keeping the end for a failure notification.
    tail = collections.deque(maxlen=12)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        print(line, end="", flush=True)
        tail.append(line.rstrip())
    code = proc.wait()
    mins = (time.monotonic() - start) / 60
    log(f"Sync {'finished' if code == 0 else f'FAILED (exit code {code})'} after {mins:.1f} min")

    if code == EXIT_NOT_LOGGED_IN:
        notify("Bandcamp Download: login cookie expired",
               "The daily sync can't log in to Bandcamp, so new shows won't download.\n"
               "Fix: on the server, in the bandcamp_download folder, run\n"
               "  python3 bandcamp_download.py --set-identity\n"
               "then: docker compose up -d",
               priority="high", tags="warning,key")
    elif code != 0:
        notify("Bandcamp Download: sync failed",
               f"Exit code {code}. Last output:\n" + "\n".join(l for l in tail if l.strip()),
               priority="high", tags="warning")


def clean_leftovers():
    """Remove temp folders left behind if the container was stopped mid-download.
    TEMP_DIR is only used by this container, so anything matching is ours."""
    temp = os.environ.get("BANDCAMP_TEMP_DIR")
    if not temp or not os.path.isdir(temp):
        return
    for name in os.listdir(temp):
        if name.startswith("bandcamp-dl-"):
            path = os.path.join(temp, name)
            log(f"Removing leftover temp folder from an interrupted run: {path}")
            shutil.rmtree(path, ignore_errors=True)


def main():
    if "--test-notify" in sys.argv[1:]:
        if not os.environ.get("NOTIFY_URL", "").strip():
            sys.exit("NOTIFY_URL isn't set in .env")
        ok = notify("Bandcamp Download: test", "Notifications are working.", tags="white_check_mark")
        sys.exit(0 if ok else 1)
    # `docker stop` sends SIGTERM; exit right away instead of waiting out the sleep.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    clean_leftovers()
    at = parse_time(os.environ.get("SYNC_TIME", "04:00"))
    tz = os.environ.get("TZ", "UTC")
    log(f"Bandcamp Download 2.0 scheduler started: daily at {at:%H:%M} ({tz}), "
        f"syncing into {os.environ.get('BANDCAMP_SYNC_DEST', '?')}")
    if os.environ.get("RUN_ON_START", "").lower() in ("1", "true", "yes"):
        run_sync()
    while True:
        when = next_run(at)
        log(f"Next sync at {when:%Y-%m-%d %H:%M}")
        # Sleep in short steps so a clock change or a laptop-style suspend can't make us skip a day.
        while datetime.datetime.now() < when:
            time.sleep(min(60, max(1, (when - datetime.datetime.now()).total_seconds())))
        run_sync()


if __name__ == "__main__":
    main()
