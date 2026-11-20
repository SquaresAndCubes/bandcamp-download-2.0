#!/usr/bin/env python3
"""
Bandcamp Download 2.0

List the most recent shows in a Bandcamp fan collection, pick which ones to
download, and download them.

Runs on Windows, macOS and Linux with Python 3.8+ (standard library only).
On Windows, run it with `py` instead of `python3`.

Setup: copy .env.example to .env (next to this script) and set
BANDCAMP_COLLECTION_URL to your collection, e.g. https://bandcamp.com/your-username,
and BANDCAMP_SYNC_DEST to your music folder (used by --sync / --fix-names).
Or pass --url and --dest each time.

Bandcamp only exposes download links to the logged-in owner of the collection,
so this script needs your Bandcamp `identity` cookie:

  1. Log in at https://bandcamp.com in your browser.
  2. Open DevTools -> Application/Storage -> Cookies -> https://bandcamp.com
  3. Copy the value of the cookie named `identity`.
  4. Run:  python3 bandcamp_download.py --set-identity   (paste it; it's checked,
     then saved to identity.txt and .env next to this script). Or save it in
     identity.txt yourself (one line), or set BANDCAMP_IDENTITY='<value>'.

At the prompt, enter numbers like `1`, `1,3`, `2-5`, `a` for all, Enter for the
newest show, or `q` to quit.

Each show is extracted into a folder named after the slug in its Bandcamp URL,
e.g. https://sts9.bandcamp.com/album/20261114-royal-oak-music-theatre-royal-oak-mi
-> <dest>/20261114-royal-oak-music-theatre-royal-oak-mi/. The .zip files are never
kept: they go in a temp folder (bandcamp-dl-<random>, in ~/Downloads by default)
that is deleted after each show, even if the download or extraction fails.
Shows whose folder already exists are skipped.

Options:
  --count N  how many recent shows to list (default: 10)
  --latest   skip the prompt and download only the newest show
  --format   flac | mp3-320 | mp3-v0 | aac-hi | vorbis | alac | wav | aiff-lossless  (default: flac)
  --dest     folder the extracted show folders go in (default: current directory)
             (--out still works as another name for --dest)
  --list     just show the list, don't download
  --dry-run  resolve the download URLs but don't download the files
             (with --latest: a quick check that the login works)
  --url      the Bandcamp collection URL (default: BANDCAMP_COLLECTION_URL in .env)

Sync mode:
  --sync     scan the WHOLE collection and download every show that isn't
             already in --dest (default: BANDCAMP_SYNC_DEST in .env). Lists what's
             missing and asks before downloading. Combine with --list to only see
             what's missing. Folders named differently (older Bandcamp names,
             other date formats) still count if the date and venue match.
  --band     only sync these artists, comma-separated, e.g. "STS9,David Phipps"
             (default: STS9; use 'all' for everything)
  --yes, -y  don't ask for confirmation (e.g. for a scheduled job)
  --allow-empty  allow syncing into an empty folder (normally refused, since it
             usually means the wrong path, or a share or drive that isn't mounted)

Fixing folder names:
  --fix-names  rename existing show folders in --dest (default: the sync folder)
               whose names don't match the current Bandcamp slug, e.g. because
               Bandcamp renamed the release. Shows every rename and asks first;
               add --list to only preview. Writes undo_renames_<time>.sh (.cmd on
               Windows) next to this script to reverse it.

Login:
  --set-identity  paste a new identity cookie (input hidden, or piped in); it's
               checked with Bandcamp, then saved to identity.txt and .env.

Notifications:
  If NOTIFY_URL is set (an ntfy topic, e.g. https://ntfy.sh/your-long-random-topic),
  every show that downloads sends a push notification, however the script was
  started (picker, --latest, --sync, by hand or by the Docker scheduler), and
  every --sync ends with a summary notification, even when nothing was new.
  NOTIFY_DOWNLOADS=false / NOTIFY_SYNC=false turn these off; NOTIFY_TOKEN is for
  protected topics.

Settings come from environment variables or the matching lines in .env
(BANDCAMP_IDENTITY, BANDCAMP_COLLECTION_URL, BANDCAMP_SYNC_DEST,
BANDCAMP_SYNC_BAND, BANDCAMP_TEMP_DIR, BANDCAMP_LOG_DIR, NOTIFY_URL,
NOTIFY_DOWNLOADS, NOTIFY_SYNC, NOTIFY_TOKEN); see the constants below.

Exit codes: 0 ok, 1 error or some shows failed, 3 not logged in.
"""

import argparse
import concurrent.futures
import html
import http.cookiejar
import json
import os
import re
import shlex
import shutil
import ssl
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile

def load_env_file(path):
    """Read BANDCAMP_* and NOTIFY_* settings from a .env file (KEY=value lines) next to this
    script, so your own collection, folders and cookie live in that private file
    instead of in the code. Real environment variables win over the file."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError:
        return
    for line in lines:
        m = re.match(r"\s*((?:BANDCAMP|NOTIFY)_[A-Z_]+)\s*=\s*(.*?)\s*$", line)
        if m and m.group(1) not in os.environ:
            value = m.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if value:
                os.environ[m.group(1)] = value


load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Settings. Each comes from the environment variable named here, or from the same
# line in .env next to this script (see .env.example).
# Your collection, e.g. https://bandcamp.com/your-username [BANDCAMP_COLLECTION_URL]
COLLECTION_URL = os.environ.get("BANDCAMP_COLLECTION_URL") or ""
# Login cookie: BANDCAMP_IDENTITY, else the contents of identity.txt next to this script.
DEFAULT_IDENTITY = ""
IDENTITY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "identity.txt")
SYNC_DEST = os.environ.get("BANDCAMP_SYNC_DEST") or ""  # default --dest for --sync / --fix-names
SYNC_BAND = os.environ.get("BANDCAMP_SYNC_BAND") or "STS9"                      # default --band for --sync
# Where zips are downloaded and unpacked temporarily [BANDCAMP_TEMP_DIR]
TEMP_ROOT = os.environ.get("BANDCAMP_TEMP_DIR") or os.path.expanduser("~/Downloads")
# Undo scripts from --fix-names go here [BANDCAMP_LOG_DIR]
LOG_DIR = os.environ.get("BANDCAMP_LOG_DIR") or os.path.dirname(os.path.abspath(__file__))
# Push notification for each downloaded show, via ntfy [NOTIFY_URL, NOTIFY_DOWNLOADS, NOTIFY_TOKEN]
NOTIFY_URL = (os.environ.get("NOTIFY_URL") or "").strip()
NOTIFY_DOWNLOADS = (os.environ.get("NOTIFY_DOWNLOADS") or "true").strip().lower() in ("1", "true", "yes")
# Summary notification at the end of every --sync, even when nothing was new [NOTIFY_SYNC]
NOTIFY_SYNC = (os.environ.get("NOTIFY_SYNC") or "true").strip().lower() in ("1", "true", "yes")
for _stream in (sys.stdout, sys.stderr):
    try:  # a console that can't show a character (e.g. on Windows) prints ? instead of crashing
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
INTERACTIVE = sys.stdout.isatty()  # in Docker logs, show progress in steps instead of live
COPY_WORKERS = 4         # files copied to --dest at the same time
COPY_CHUNK = 4 * 2**20   # 4 MB reads/writes; fine locally, and large chunks help on network shares
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


class DownloadError(Exception):
    pass


def send_notification(title, message, tags="", priority="default"):
    """Post to NOTIFY_URL (ntfy). Never stops the run if it can't be sent."""
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags
    token = (os.environ.get("NOTIFY_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(NOTIFY_URL, data=message.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print("  Notification sent")
    except Exception as e:
        print(f"  (Couldn't send notification: {e})")


def notify_download(title, dest):
    """One notification per downloaded show [NOTIFY_DOWNLOADS]."""
    if NOTIFY_URL and NOTIFY_DOWNLOADS:
        send_notification("Bandcamp Download: new show",
                          f"{title}\n{os.path.basename(dest)}", tags="musical_note")


def notify_sync_done(n_saved, failed, n_total, dest):
    """Summary at the end of every --sync, including when nothing was new [NOTIFY_SYNC]."""
    if not (NOTIFY_URL and NOTIFY_SYNC):
        return
    have = n_total - len(failed)
    if failed:
        send_notification(
            f"Bandcamp Download: sync done, {len(failed)} failed",
            f"{n_saved} new, {len(failed)} failed:\n" + "\n".join(failed)
            + f"\n{have} of {n_total} shows in {dest}",
            tags="warning", priority="high")
    elif n_saved:
        send_notification(
            f"Bandcamp Download: sync done, {n_saved} new show{'s' if n_saved != 1 else ''}",
            f"All {n_total} shows are in {dest}", tags="white_check_mark")
    else:
        send_notification("Bandcamp Download: sync done, nothing new",
                          f"All {n_total} shows are already in {dest}", tags="white_check_mark")


def build_opener(identity):
    jar = http.cookiejar.CookieJar()
    if identity:
        jar.set_cookie(http.cookiejar.Cookie(
            0, "identity", identity, None, False, ".bandcamp.com", True, True,
            "/", True, True, None, False, None, None, {}))
    # python.org builds on macOS often ship without CA certs; fall back to the system bundle.
    ctx = ssl.create_default_context()
    if not ctx.get_ca_certs() and os.path.exists("/etc/ssl/cert.pem"):
        ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), urllib.request.HTTPSHandler(context=ctx))
    opener.addheaders = [("User-Agent", UA)]
    return opener


def fetch(opener, url):
    with opener.open(url, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def pagedata(page):
    m = re.search(r'id="pagedata"\s+data-blob="([^"]+)"', page)
    if not m:
        raise DownloadError("Could not find page data; Bandcamp's page layout may have changed.")
    return json.loads(html.unescape(m.group(1)))


def latest_items(data, n=1):
    cd = data["collection_data"]
    cache = data["item_cache"]["collection"]
    seq = cd.get("sequence") or list(cache.keys())
    return [cache[k] for k in seq[:n] if k in cache]


def resolve_download(opener, redownload_page_url, fmt):
    data = pagedata(fetch(opener, redownload_page_url))
    items = data.get("digital_items") or []
    if not items:
        raise DownloadError("Download page had no digital items.")
    downloads = items[0].get("downloads") or {}
    if fmt not in downloads:
        raise DownloadError(f"Format '{fmt}' not available. Choices: {', '.join(downloads)}")
    url = downloads[fmt]["url"]

    # Bandcamp prepares the zip on demand; poll the "statdownload" endpoint until ready.
    stat = url.replace("/download/", "/statdownload/")
    stat += ("&" if "?" in stat else "?") + ".vrs=1"
    for _ in range(30):
        try:
            body = fetch(opener, stat)
            js = json.loads(re.search(r"\{.*\}", body, re.S).group(0))
        except Exception:
            break  # fall back to the original URL
        if js.get("result") == "ok":
            return js.get("download_url") or url
        if js.get("retry_url"):
            stat = js["retry_url"]
        time.sleep(2)
    return url


def safe_name(s):
    """Make a string safe as a file or folder name on macOS, Linux and Windows."""
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", s).strip()
    return s.rstrip(". ") or "_"  # Windows drops trailing dots and spaces


class Progress:
    """MB done / total with speed. Live-updating in a terminal; in logs (Docker),
    one line at each 25% so the log doesn't fill up."""

    def __init__(self, label):
        self.label, self.start, self.next_step, self.shown = label, time.monotonic(), 25, False

    def update(self, done, total):
        speed = done / 1e6 / max(time.monotonic() - self.start, 1e-6)
        line = f"  {self.label}: {done / 1e6:7.1f} / {total / 1e6:.1f} MB  ({speed:.1f} MB/s)"
        if INTERACTIVE:
            print("\r" + line, end="", flush=True)
            self.shown = True
        elif done * 100 >= self.next_step * total:
            print(line, flush=True)
            self.next_step = (done * 100 // total // 25 + 1) * 25

    def finish(self):
        if self.shown:
            print()
            self.shown = False


def download(opener, url, out_dir, fallback_name):
    with opener.open(url, timeout=120) as r:
        name = fallback_name
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
        if m:
            name = safe_name(urllib.parse.unquote(m.group(1)))
        path = os.path.join(out_dir, name)
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        progress = Progress("Downloaded")
        with open(path + ".part", "wb") as f:
            while chunk := r.read(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if total:
                    progress.update(done, total)
        progress.finish()
    os.replace(path + ".part", path)
    return path


def band_matches(item, band):
    """--band filter: 'all', or a comma-separated list of artist names (any case)."""
    wanted = {b.strip().lower() for b in band.split(",") if b.strip()}
    return "all" in wanted or item.get("band_name", "").strip().lower() in wanted


def show_slug(item):
    """The show's slug from its Bandcamp URL, e.g. .../album/20261114-royal-oak-music-theatre-royal-oak-mi."""
    slug = (item.get("url_hints") or {}).get("slug")
    if not slug and item.get("item_url"):
        slug = urllib.parse.urlparse(item["item_url"]).path.rstrip("/").rsplit("/", 1)[-1]
    return safe_name(slug or f"{item['band_name']} - {item['item_title']}")


def extract(path, dest):
    """Unpack a downloaded zip into dest and delete the zip.
    Single-track downloads aren't zips, so they're moved in as-is."""
    os.makedirs(dest, exist_ok=True)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            z.extractall(dest)  # zipfile strips absolute paths and '..' from member names
        os.remove(path)
    else:
        shutil.move(path, os.path.join(dest, os.path.basename(path)))
    return dest


def copy_tree_fast(src, dst, workers=COPY_WORKERS):
    """Copy the extracted show to its destination (a local folder or a network share;
    the tricks below matter most on a share):
    - copies file contents only (no timestamps/permissions/xattrs, which cost extra
      round trips per file on SMB/NFS),
    - copies several files at once so per-file latency overlaps,
    - prints overall progress and speed."""
    files = []
    for root, _, names in os.walk(src):
        rel = os.path.relpath(root, src)
        os.makedirs(os.path.normpath(os.path.join(dst, rel)), exist_ok=True)
        for name in names:
            s = os.path.join(root, name)
            files.append((s, os.path.normpath(os.path.join(dst, rel, name)), os.path.getsize(s)))
    total = sum(size for _, _, size in files) or 1
    done = 0
    lock = threading.Lock()
    start = time.monotonic()
    progress = Progress("Copied")

    def report(n):
        nonlocal done
        with lock:
            done += n
            progress.update(done, total)

    def copy_one(s, d):
        with open(s, "rb") as fi, open(d, "wb") as fo:
            while chunk := fi.read(COPY_CHUNK):
                fo.write(chunk)
                report(len(chunk))

    print(f"  Copying {len(files)} files ({total / 1e6:.1f} MB) to {dst}, {workers} at a time...")
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(copy_one, s, d) for s, d, _ in files]
            for f in concurrent.futures.as_completed(futures):
                f.result()  # re-raise the first copy error
    finally:
        progress.finish()  # end the progress line
    print(f"  Copied in {time.monotonic() - start:.1f}s")


def download_show(opener, url, dest_root, slug, fallback_name):
    """Download and extract one show into dest_root/slug.
    The zip is downloaded and extracted in a temp folder in ~/Downloads that is
    always deleted, so no .zip (or partial show folder) is ever left behind,
    even if something fails midway."""
    os.makedirs(TEMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="bandcamp-dl-", dir=TEMP_ROOT)
    final = os.path.join(dest_root, slug)
    try:
        print(f"  Downloading to {tmp} ...")
        path = download(opener, url, tmp, fallback_name)
        print("  Extracting...")
        staged = extract(path, os.path.join(tmp, "show"))
        try:
            copy_tree_fast(staged, final)
        except BaseException:
            shutil.rmtree(final, ignore_errors=True)  # don't leave a half-copied show
            raise
        return final
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def is_downloaded(dest_root, item):
    """A show counts as downloaded if its slug-named folder exists and isn't empty."""
    d = os.path.join(dest_root, show_slug(item))
    return os.path.isdir(d) and any(not n.startswith(".") for n in os.listdir(d))


def find_date(s):
    """Pull a show date out of a slug, folder name or title, as 'YYYYMMDD'.
    Handles 20161229, 2017-12-04, 2018-1124, 2026.05.08 and 050826 (MMDDYY)."""
    s = s.replace("​", "")  # some Bandcamp titles contain zero-width spaces
    patterns = [(r"(?<!\d)((?:19|20)\d\d)[.\-]?(\d\d)[.\-]?(\d\d)(?!\d)", "ymd"),
                (r"(?<!\d)((?:19|20)\d\d)-(\d\d)(\d\d)(?!\d)", "ymd"),
                (r"^(\d\d)(\d\d)(\d\d)(?!\d)", "mdy")]
    for pattern, kind in patterns:
        for m in re.finditer(pattern, s):
            a, b, c = m.groups()
            y, mo, d = (a, b, c) if kind == "ymd" else ("20" + c, a, b)
            if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
                return f"{y}{mo}{d}"
    return None


_STOPWORDS = {"the", "at", "of", "and", "in", "live", "night", "set", "sets", "music", "festival"}


def name_words(s):
    """Distinctive words in a name, plus a night tag like 'n2' for 'night-2' / 'N2'."""
    s = s.lower().replace("​", "")
    nights = {f"n{d}" for d in re.findall(r"(?:night|\bn)[\s\-_]*(\d)(?!\d)", s)}
    s = re.sub(r"\d+", " ", s)
    words = {w for w in re.split(r"[^a-z]+", s) if len(w) > 1 and w not in _STOPWORDS}
    return words | nights


def nights_conflict(a, b):
    """True if the two names can't be the same release: both say which night it
    was and disagree (N1 vs night-2), or only one of them is a soundcheck."""
    if ("soundcheck" in a) != ("soundcheck" in b):
        return True
    na = {w for w in a if re.fullmatch(r"n\d", w)}
    nb = {w for w in b if re.fullmatch(r"n\d", w)}
    return bool(na and nb and not (na & nb))


def days_apart(a, b):
    import datetime
    try:
        da, db = (datetime.date(int(x[:4]), int(x[4:6]), int(x[6:])) for x in (a, b))
    except ValueError:
        return 999
    return abs((da - db).days)


def match_existing(dest_root, items):
    """Work out which items are already in dest_root.
    Folders are normally named by slug, but Bandcamp sometimes renames releases
    after you've downloaded them, and older folders may use other date formats.
    So an item also counts as downloaded if an otherwise-unclaimed folder has
      1. the same show date and at least one venue word in common
         (or is the only unclaimed folder with that date), or
      2. a date within 3 days and at least 3 venue words in common.
    Returns (missing_items, fuzzy_matches) where fuzzy_matches is [(item, folder)]."""
    # One directory read for everything: checking each show folder separately is
    # fine locally but takes minutes on a network share.
    with os.scandir(dest_root) as entries:
        folders = {e.name for e in entries if not e.name.startswith(".") and e.is_dir()}
    slugs = {show_slug(it) for it in items}
    unmatched = [it for it in items if show_slug(it) not in folders]
    spare = [f for f in folders if f not in slugs]
    spare_info = {f: (find_date(f), name_words(f)) for f in spare}
    fuzzy = []

    def item_info(it):
        return (find_date(it.get("item_title", "")) or find_date(show_slug(it)),
                name_words(show_slug(it)) | name_words(it.get("item_title", "")))

    for exact in (True, False):  # exact-date pass first, so near-dates can't steal a folder
        # Score every possible (show, folder) pair, then take the best pairs first.
        pairs = []
        for i, it in enumerate(unmatched):
            date, words = item_info(it)
            if not date:
                continue
            cands = []
            for f in spare:
                fdate, fwords = spare_info[f]
                if not fdate or nights_conflict(words, fwords):
                    continue
                overlap, gap = len(words & fwords), days_apart(fdate, date)
                if (exact and gap == 0) or (not exact and 0 < gap <= 3 and overlap >= 3):
                    cands.append((overlap, -gap, i, f))
            if exact and not any(c[0] >= 1 for c in cands) and len(cands) != 1:
                cands = []  # same date but nothing in common and not unique: too risky
            pairs += cands
        taken_items, taken_folders = set(), set()
        for overlap, _, i, f in sorted(pairs, reverse=True):
            if i not in taken_items and f not in taken_folders:
                taken_items.add(i)
                taken_folders.add(f)
                fuzzy.append((unmatched[i], f))
        spare = [f for f in spare if f not in taken_folders]
        unmatched = [it for i, it in enumerate(unmatched) if i not in taken_items]
    return unmatched, fuzzy


def fix_folder_names(opener, data, args):
    """Rename existing show folders whose names don't match the Bandcamp slug
    (e.g. renamed releases, other date formats) to the current slug.
    Previews everything, asks first, and writes an undo script."""
    if not os.path.isdir(args.dest):
        sys.exit(f"{args.dest} doesn't exist. Check the path (and, if it's on a "
                 "network share or external drive, that it's mounted).")
    print("Scanning the whole collection...")
    shows = [it for it in fetch_all_items(opener, data, {})
             if band_matches(it, args.band)]
    _, fuzzy = match_existing(args.dest, shows)
    renames = []
    for it, folder in fuzzy:
        new = show_slug(it)
        if new != folder and not os.path.exists(os.path.join(args.dest, new)):
            near = find_date(folder) != (find_date(it.get("item_title", "")) or find_date(new))
            renames.append((folder, new, near))
    if not renames:
        print("All folder names already match Bandcamp.")
        return
    renames.sort(key=lambda r: (r[2], r[1]))
    print(f"\n{len(renames)} folders to rename in {args.dest}:")
    for n, (old, new, near) in enumerate(renames, 1):
        tag = "  [date differs: check this one]" if near else ""
        print(f"  {n:>3}. {old}\n       -> {new}{tag}")
    if args.list or args.dry_run:
        return
    if not args.yes:
        try:
            ok = input(f"\nRename these {len(renames)} folders? [y/N] ")
        except EOFError:
            ok = ""
        if ok.strip().lower() not in ("y", "yes"):
            print("Cancelled. Nothing renamed.")
            return
    os.makedirs(LOG_DIR, exist_ok=True)
    windows = os.name == "nt"
    log_path = os.path.join(LOG_DIR, time.strftime("undo_renames_%Y%m%d-%H%M%S")
                            + (".cmd" if windows else ".sh"))

    def cmd_quote(x):  # Windows names can't contain ", but % would be expanded in a .cmd
        return '"' + x.replace("%", "%%") + '"'

    done = 0
    with open(log_path, "w", encoding="utf-8") as log:
        if windows:
            log.write("@echo off\nchcp 65001 >nul\nREM Run this to undo the folder renames made by --fix-names.\n")
            log.write(f"cd /d {cmd_quote(args.dest)} || exit /b 1\n")
        else:
            log.write("#!/bin/sh\n# Run this to undo the folder renames made by --fix-names.\n")
            log.write(f"cd {shlex.quote(args.dest)} || exit 1\n")
        for old, new, _ in renames:
            try:
                os.rename(os.path.join(args.dest, old), os.path.join(args.dest, new))
            except OSError as e:
                print(f"  Failed: {old}: {e}")
                continue
            if windows:
                log.write(f"if not exist {cmd_quote(old)} ren {cmd_quote(new)} {cmd_quote(old)}\n")
            else:
                log.write(f"mv -n {shlex.quote(new)} {shlex.quote(old)}\n")
            log.flush()
            done += 1
    print(f"\nRenamed {done} of {len(renames)} folders.")
    print(f"To undo: {cmd_quote(log_path)}" if windows else f"To undo: sh {shlex.quote(log_path)}")


def fetch_all_items(opener, data, redownload_urls):
    """Every item in the collection, newest first. The page only embeds the first
    ~20; the rest come from Bandcamp's collection API, 500 at a time. Download
    links found along the way are added to redownload_urls."""
    cd = data["collection_data"]
    items = latest_items(data, len(data["item_cache"]["collection"]))
    seen = {(it["tralbum_type"], it["tralbum_id"]) for it in items}
    token, fan_id = cd.get("last_token"), data["fan_data"]["fan_id"]
    while token:
        req = urllib.request.Request(
            "https://bandcamp.com/api/fancollection/1/collection_items",
            data=json.dumps({"fan_id": fan_id, "older_than_token": token, "count": 500}).encode(),
            headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=60) as r:
            page = json.load(r)
        for it in page.get("items") or []:
            key = (it["tralbum_type"], it["tralbum_id"])
            if key not in seen:
                seen.add(key)
                items.append(it)
        redownload_urls.update(page.get("redownload_urls") or {})
        if INTERACTIVE:
            print(f"\r  {len(items)} / {cd.get('item_count', '?')} items", end="", flush=True)
        token = page.get("last_token") if page.get("more_available") else None
    print(f"\r  {len(items)} / {cd.get('item_count', '?')} items" if INTERACTIVE
          else f"  {len(items)} items")
    return items


def print_menu(items):
    width = len(str(len(items)))
    for i, it in enumerate(items, 1):
        added = (it.get("purchased") or "")[:11]
        flag = "" if it.get("download_available", True) else "  (no download)"
        print(f"  {i:>{width}}. [{added}] {it['band_name']} - {it['item_title']}{flag}")


def parse_selection(text, n):
    """Turn '1,3-5' / 'a' / '' into a sorted list of 0-based indexes. Returns None to quit."""
    text = text.strip().lower()
    if text in ("q", "quit", "exit"):
        return None
    if text == "":
        return [0]
    if text in ("a", "all", "*"):
        return list(range(n))
    picks = set()
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            raise ValueError(f"'{part}' isn't a number or range")
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        if lo > hi:
            lo, hi = hi, lo
        if lo < 1 or hi > n:
            raise ValueError(f"'{part}' is out of range (1-{n})")
        picks.update(range(lo - 1, hi))
    return sorted(picks)


def ask_selection(items):
    print_menu(items)
    while True:
        try:
            text = input("\nWhich shows? (e.g. 1,3 or 2-5, a = all, Enter = newest, q = quit): ")
        except EOFError:
            return []
        try:
            sel = parse_selection(text, len(items))
        except ValueError as e:
            print(f"  {e}. Try again.")
            continue
        return [] if sel is None else [items[i] for i in sel]


EXIT_NOT_LOGGED_IN = 3  # the scheduler uses this to send a "cookie expired" alert


def logged_in(data):
    """True if the cookie is logged in as the owner of this collection
    (only the owner gets download links)."""
    me = (data.get("current_fan") or {}).get("fan_id")
    return bool(me) and me == (data.get("fan_data") or {}).get("fan_id")


def not_logged_in():
    print("Not logged in: the Bandcamp identity cookie is missing, expired, or for a different "
          "account. Get a new one and run: python3 bandcamp_download.py --set-identity",
          file=sys.stderr, flush=True)
    sys.exit(EXIT_NOT_LOGGED_IN)


def set_identity(collection_url):
    """Ask for a new identity cookie (input hidden), check it's logged in to the
    collection's account, then save it to identity.txt and .env next to this script."""
    import getpass
    print("Paste your Bandcamp `identity` cookie value. Get it by logging in at bandcamp.com,\n"
          "then DevTools -> Application (Storage in Firefox) -> Cookies -> https://bandcamp.com -> identity.\n"
          "(What you paste isn't shown.)")
    try:
        raw = getpass.getpass("identity cookie: ") if sys.stdin.isatty() else sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\nCancelled. Nothing saved.")
    cookie = raw.strip().strip("'\"")
    if cookie.lower().startswith("identity="):
        cookie = cookie[len("identity="):]
    if not cookie:
        sys.exit("Nothing pasted. Nothing saved.")
    if re.search(r"[\s'\"$;]", cookie):
        sys.exit("That doesn't look like a cookie value (it has spaces, quotes, $ or ;). Nothing saved.")

    print("Checking it with Bandcamp...")
    data = pagedata(fetch(build_opener(cookie), collection_url))
    if not logged_in(data):
        sys.exit(f"That cookie isn't logged in to the account that owns {collection_url}. "
                 "Nothing saved. (Copied the whole value? Logged in to the right account?)")
    print(f"Works: logged in as {(data.get('fan_data') or {}).get('username')}.")

    here = os.path.dirname(os.path.abspath(__file__))

    def write_private(path, text):
        tmp = path + ".new"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)

    write_private(IDENTITY_FILE, cookie + "\n")
    print(f"Saved to {IDENTITY_FILE}")
    env_path = os.path.join(here, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
        new_line = f"BANDCAMP_IDENTITY='{cookie}'"
        if any(l.startswith("BANDCAMP_IDENTITY=") for l in lines):
            lines = [new_line if l.startswith("BANDCAMP_IDENTITY=") else l for l in lines]
        else:
            lines.insert(0, new_line)
        write_private(env_path, "\n".join(lines) + "\n")
        print(f"Saved to {env_path}")
        print("If the Docker container is running, apply it with:  docker compose up -d")


def main():
    ap = argparse.ArgumentParser(description="Pick and download recent shows from a Bandcamp collection.")
    ap.add_argument("--url", default=COLLECTION_URL,
                    help="your Bandcamp collection, e.g. https://bandcamp.com/your-username "
                         "(default: BANDCAMP_COLLECTION_URL in .env)")
    ap.add_argument("--count", type=int, default=10, help="how many recent shows to list")
    ap.add_argument("--latest", action="store_true", help="download the newest show without asking")
    ap.add_argument("--format", default="flac")
    ap.add_argument("--dest", "--out",
                    help="folder to put the extracted show folders in (default: current "
                         "folder; with --sync / --fix-names, BANDCAMP_SYNC_DEST in .env)")
    ap.add_argument("--list", action="store_true", help="only list shows, don't download")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sync", action="store_true",
                    help="scan the whole collection and download every show not already in --dest")
    ap.add_argument("--band", default=SYNC_BAND,
                    help=f"with --sync, only include these artists, comma-separated "
                         f"(default: {SYNC_BAND}; 'all' for everything)")
    ap.add_argument("--allow-empty", action="store_true",
                    help="let --sync download into an empty folder (normally refused, "
                         "since it usually means the wrong path or an unmounted share/drive)")
    ap.add_argument("--fix-names", action="store_true",
                    help="rename existing show folders in --dest to their current Bandcamp slug "
                         "(previews and asks first; writes an undo script)")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="with --sync or --fix-names, don't ask for confirmation")
    ap.add_argument("--set-identity", action="store_true",
                    help="paste a new Bandcamp identity cookie: checks it works, then saves it "
                         "to identity.txt and .env next to this script")
    args = ap.parse_args()
    if not args.url:
        sys.exit("Which Bandcamp collection? Set BANDCAMP_COLLECTION_URL in .env "
                 "(see .env.example), or pass --url https://bandcamp.com/your-username")
    if (args.sync or args.fix_names) and not (args.dest or SYNC_DEST):
        sys.exit("Which music folder? Pass --dest /path/to/music, "
                 "or set BANDCAMP_SYNC_DEST in .env (see .env.example).")
    args.dest = os.path.abspath(os.path.expanduser(
        args.dest or (SYNC_DEST if (args.sync or args.fix_names) else ".")))

    if args.set_identity:
        set_identity(args.url)
        return

    identity = os.environ.get("BANDCAMP_IDENTITY", "").strip() or DEFAULT_IDENTITY
    if not identity and os.path.exists(IDENTITY_FILE):
        with open(IDENTITY_FILE, encoding="utf-8-sig") as f:
            identity = f.read().strip()
    opener = build_opener(identity)
    try:
        data = pagedata(fetch(opener, args.url))
    except DownloadError as e:
        sys.exit(str(e))
    redownload_urls = dict(data["collection_data"].get("redownload_urls") or {})

    # A scheduled sync checks the login every run, not only when there's something to
    # download, so an expired cookie is reported (and alerted on) straight away.
    if args.sync and not args.list and not logged_in(data):
        not_logged_in()

    if args.fix_names:
        fix_folder_names(opener, data, args)
        return

    if args.sync:
        # Don't create the folder: a typo, or a share or external drive that isn't mounted,
        # would otherwise mean downloading everything to the wrong place.
        if not os.path.isdir(args.dest):
            sys.exit(f"{args.dest} doesn't exist. Check the path (and, if it's on a "
                     "network share or external drive, that it's mounted).")
        # An empty folder usually means the wrong path or an unmounted share/drive (Docker
        # creates an empty mount point), and syncing would re-download the whole collection.
        if not args.allow_empty and not any(not n.startswith(".") for n in os.listdir(args.dest)):
            sys.exit(f"{args.dest} is empty. Is that the right folder (and, if it's on a "
                     "network share or external drive, is it mounted)? "
                     "(Use --allow-empty if you really want to download everything into it.)")
        print("Scanning the whole collection...")
        all_items = fetch_all_items(opener, data, redownload_urls)
        shows = [it for it in all_items
                 if band_matches(it, args.band)]
        no_dl = [it for it in shows if not it.get("download_available")]
        shows = [it for it in shows if it.get("download_available")]
        missing, fuzzy = match_existing(args.dest, shows)
        print(f"{len(all_items)} items in collection, {len(shows)} downloadable by {args.band}, "
              f"{len(shows) - len(missing)} already in {args.dest}.")
        if fuzzy:
            print(f"\nCounted as already downloaded because a folder with a different name matches "
                  f"({len(fuzzy)}):")
            for it, folder in fuzzy:
                print(f"  {show_slug(it)}  ~  {folder}")
        for it in no_dl:
            print(f"  (skipping, no download on Bandcamp: {it['item_title']})")
        if not missing:
            print("Nothing to download: everything is already there.")
            if not args.list and not args.dry_run:
                notify_sync_done(0, [], len(shows), args.dest)
            return
        print(f"\n{len(missing)} not downloaded yet:")
        print_menu(missing)
        if args.list:
            return
        if not args.yes and not args.dry_run:
            try:
                noun = "show" if len(missing) == 1 else "shows"
                ok = input(f"\nDownload {len(missing)} {noun} to {args.dest}? [y/N] ")
            except EOFError:
                ok = ""
            if ok.strip().lower() not in ("y", "yes"):
                print("Cancelled.")
                return
        chosen = missing
    else:
        items = latest_items(data, max(args.count, 1))
        if not items:
            sys.exit("The collection is empty.")

        if args.list:
            print_menu(items)
            return

        if not logged_in(data):
            not_logged_in()

        chosen = [items[0]] if args.latest else ask_selection(items)
        if not chosen:
            print("Nothing selected.")
            return

    os.makedirs(args.dest, exist_ok=True)
    if not args.dry_run:
        # Fail once, clearly, instead of every show failing the same way.
        try:
            os.makedirs(TEMP_ROOT, exist_ok=True)
            os.rmdir(tempfile.mkdtemp(prefix="bandcamp-dl-check-", dir=TEMP_ROOT))
        except OSError as e:
            sys.exit(f"Can't write to the temp folder {TEMP_ROOT}: {e}\n"
                     "(In Docker: check TEMP_DIR in .env exists and is owned by PUID/PGID.)")
    saved, failed = [], []
    for n, item in enumerate(chosen, 1):
        title = f"{item['band_name']} - {item['item_title']}"
        print(f"\n[{n}/{len(chosen)}] {title}")
        dest = os.path.join(args.dest, show_slug(item))
        if is_downloaded(args.dest, item) and not args.dry_run:
            print(f"  Already downloaded: {dest} (skipping)")
            saved.append(dest)
            continue
        try:
            redl = redownload_urls.get(f"{item['sale_item_type']}{item['sale_item_id']}")
            if not redl:
                raise DownloadError("no download link for this item")
            url = resolve_download(opener, redl, args.format)
            if args.dry_run:
                print("  Download URL:", url)
                saved.append(title)
                continue
            print(f"  Format: {args.format}")
            download_show(opener, url, args.dest, show_slug(item), safe_name(title) + ".zip")
            print("  Saved to:", dest)
            saved.append(dest)
            notify_download(title, dest)
        except Exception as e:
            print(f"  Failed: {e}")
            failed.append(title)

    print(f"\nDone: {len(saved)} succeeded, {len(failed)} failed.")
    for t in failed:
        print("  failed:", t)
    if args.sync and not args.dry_run:
        notify_sync_done(len(saved), failed, len(shows), args.dest)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
